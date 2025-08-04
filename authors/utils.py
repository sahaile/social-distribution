import urllib.parse
import uuid
from typing import TYPE_CHECKING
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework.exceptions import (
    APIException
)
from entries.models import Entry, Comment

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    Author = AbstractUser
else:
    Author = get_user_model()


class NotImplementedException(APIException):
    status_code = 501
    default_detail = 'Remote author lookup (via FQID) is not supported.'
    default_code = 'not_implemented'


class RemoteConnectionError(APIException):
    status_code = 502
    default_detail = 'Could not connect to remote host.'
    default_code = 'remote_connection_error'


def get_author_from_identifier(serial_or_fqid, request=None):
    """
    Helper method to resolve an author from a local serial or a
    fully-qualified ID (FQID).

    - If the identifier is a local serial or a local FQID, it returns the
      corresponding local Author object.
    - If the identifier is a remote FQID, it returns the FQID string itself.
    - Raises Http404 for invalid formats.
    - When resolving an FQID, a `request` object must be provided.
    """
    decoded_identifier = urllib.parse.unquote(serial_or_fqid)

    # Check if it's a URL (FQID).
    if decoded_identifier.startswith('http'):
        if not request:
            raise ValueError(
                "A request object must be provided to resolve an FQID."
            )
        try:
            # Assumes the last part of the path is the author's serial
            parsed_url = urllib.parse.urlparse(decoded_identifier)
            author_serial = parsed_url.path.rstrip('/').split('/')[-1]
            uuid.UUID(author_serial)  # Validate UUID format

            # Check if this FQID is local or remote by comparing hosts
            local_host = request.get_host()
            if parsed_url.netloc == local_host:
                # It's a local FQID.
                return get_object_or_404(Author, serial=author_serial)
            else:
                # It's a remote FQID. Return it for proxying.
                return decoded_identifier

        except (ValueError, ValidationError, IndexError):
            raise Http404(
                "Author not found or invalid FQID format."
            )

    # Not an FQID, treat as a direct serial.
    try:
        # Validate if it's a UUID format
        uuid.UUID(decoded_identifier)
        # If it's a valid UUID format, look it up
        return get_object_or_404(Author, serial=decoded_identifier)
    except (ValueError, ValidationError):
        # Not a valid UUID format or Django raised ValidationError.
        raise Http404("Author not found or invalid serial format.")


def get_or_create_proxy_author(author_data: dict, request=None) -> Author:
    """
    Finds an existing author by their URL or creates a proxy representation
    for a remote author. This is essential for creating relationships
    (e.g., Follows)
    with authors who do not exist on the local server.

    If the author already exists, it will update their information with any
    new data provided, ensuring the local proxy stays synchronized with
    remote changes.

    Args:
        author_data: A dictionary representing the author, conforming to the
                     project spec's author object format.
        request: Optional request object to determine current host dynamically

    Returns:
        The existing or newly created Author instance.
    """
    author_url = author_data.get('id')
    if not author_url:
        raise ValueError("Author data must include an 'id' (URL).")

    # Get current host - use request if available, otherwise fallback to
    # settings
    if request:
        current_host = f"{request.scheme}://{request.get_host()}/"
    else:
        from django.conf import settings
        current_host = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000/')
        if not current_host.endswith('/'):
            current_host += '/'

    author_host = author_data.get('host', '')
    if not author_host.endswith('/'):
        author_host += '/'

    # Don't create proxy authors for local authors - return existing if found
    if author_host == current_host:
        try:
            # Try to find the existing local author by URL
            return Author.objects.get(url=author_url)
        except Author.DoesNotExist:
            # If local author doesn't exist, something is wrong
            raise ValueError(f"Local author with URL {author_url} not found")

    # Extract the serial from the remote author's URL
    # URL format: http://host/api/authors/{serial}/ or {serial}
    try:
        parsed_url = urllib.parse.urlparse(author_url)
        path_parts = parsed_url.path.rstrip('/').split('/')
        author_serial = path_parts[-1]

        # Handle cases where the URL might be malformed
        if not author_serial:
            raise ValueError("Empty serial in URL")

        # Validate UUID format - be more flexible with validation
        try:
            uuid_obj = uuid.UUID(author_serial)
            author_serial = str(uuid_obj)  # Normalize the UUID format
        except ValueError:
            # If it's not a valid UUID, we still try to use it
            # Some nodes might use different ID formats
            pass

    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid author URL format: {author_url} - {e}")

    try:
        # Try to get existing author by URL first
        author = Author.objects.get(url=author_url)
        # Update existing author with new data
        _update_author_fields(author, author_data)
        author.save()
        return author
    except Author.DoesNotExist:
        # Create new proxy author
        try:
            author = Author.objects.create(
                url=author_url,
                serial=uuid.UUID(
                    author_serial) if author_serial else uuid.uuid4(),
                host=author_host,  # Use normalized host
                display_name=author_data.get('displayName', ''),
                github=author_data.get('github', ''),
                profile_image=author_data.get('profileImage', ''),
                # Remote authors are not active users on this system
                is_active=False,
                # Include part of serial for debugging
                username=f"proxy_{uuid.uuid4()}_{author_serial[:8]}",
            )
            return author
        except Exception as e:
            # Re-raise with more context
            raise ValueError(
                f"Failed to create proxy author for {
                    author_data.get(
                        'displayName',
                        'unknown')}: {e}")


def _update_author_fields(author: Author, author_data: dict) -> bool:
    """
    Internal helper to update author fields with new data.

    Args:
        author: The Author instance to update
        author_data: New author data from external source

    Returns:
        bool: True if any fields were updated, False otherwise
    """
    updated = False

    # Map of author_data keys to Author model fields
    field_mappings = {
        'displayName': 'display_name',
        'github': 'github',
        'profileImage': 'profile_image',
        'host': 'host',
    }

    for data_key, model_field in field_mappings.items():
        if data_key in author_data:
            new_value = author_data[data_key] or ''  # Handle None values
            current_value = getattr(author, model_field) or ''

            if new_value != current_value:
                setattr(author, model_field, new_value)
                updated = True

    return updated


def get_object_from_fqid(fqid: str):
    """
    Resolves a Fully Qualified ID (FQID) to a local model instance.
    Performs a direct URL lookup.

    Example FQIDs:
    - http://host/api/authors/{author_serial}/entries/{entry_serial}
    - http://host/api/authors/{author_serial}/comments/{comment_serial}
    """
    try:
        # Normalize FQID by trying both with and without trailing slash
        fqid_variants = [fqid]
        if fqid.endswith('/'):
            fqid_variants.append(fqid.rstrip('/'))
        else:
            fqid_variants.append(fqid + '/')

        # First, try to find an Entry with any of these URL variants.
        for url_variant in fqid_variants:
            entry = Entry.objects.filter(url=url_variant).first()
            if entry:
                return entry

        # If not an Entry, try to find a Comment with any of these URL
        # variants.
        for url_variant in fqid_variants:
            comment = Comment.objects.filter(url=url_variant).first()
            if comment:
                return comment

        # Try to find comment by extracting UUID from /commented/ URLs
        # and matching against comment serial
        try:
            if '/commented/' in fqid:
                comment_serial = fqid.split('/commented/')[-1].rstrip('/')
                comment = Comment.objects.filter(serial=comment_serial).first()
                if comment:
                    return comment
        except (ValueError, IndexError):
            pass

        # If no object is found by direct URL match, return None.
        return None
    except (Entry.DoesNotExist, Comment.DoesNotExist):
        return None
