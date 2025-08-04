import urllib.parse
import uuid
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404
from .models import Entry


def parse_entry_fqid(entry_fqid):
    """
    Parse an entry FQID and return the entry object.

    Args:
        entry_fqid (str): The fully qualified ID of the entry

    Returns:
        Entry: The entry object

    Raises:
        Http404: If entry is not found or FQID is malformed
    """
    try:
        decoded_fqid = urllib.parse.unquote(entry_fqid)

        # Use urlparse for robust parsing of the path
        parsed_url = urllib.parse.urlparse(decoded_fqid)
        path_parts = parsed_url.path.strip('/').split('/')

        # The FQID structure implies the entry serial
        # is the last part of the path,
        # and the author serial is the third-to-last.
        if len(path_parts) < 3:
            raise Http404("Invalid FQID path structure")

        entry_serial = path_parts[-1]
        # authors/{author_serial}/entries/{entry_serial}
        author_serial = path_parts[-3]

        # get_object_or_404 will handle lookup errors and invalid UUID formats
        return get_object_or_404(
            Entry,
            serial=entry_serial,
            author__serial=author_serial,
            is_deleted=False
        )
    except (Http404, ValueError, IndexError, AttributeError, ValidationError):
        # Catch any parsing or lookup errors and raise a consistent 404.
        raise Http404("Entry not found or FQID is malformed")


def parse_author_fqid(author_fqid):
    """
    Parse an author FQID and return the author serial.

    Args:
        author_fqid (str): The fully qualified ID of the author

    Returns:
        str: The author serial

    Raises:
        ValueError: If FQID is malformed
    """
    # URL decode first (handles percent encoding)
    decoded_fqid = urllib.parse.unquote(author_fqid)

    # Expected FQID format: http://host/api/authors/{author_serial}
    try:
        # Split the URL and extract the author serial (last part)
        path_parts = decoded_fqid.rstrip('/').split('/')
        author_serial = path_parts[-1]

        # Check if it's not empty
        if not author_serial:
            raise ValueError("Missing author serial")

        # Try to validate as UUID
        try:
            uuid.UUID(author_serial)
        except ValueError:
            # Not a valid UUID format, but still return it
            # Let the caller decide what to do with non-UUID serials
            pass

        return author_serial

    except (IndexError, AttributeError):
        raise ValueError(f"Invalid author FQID format: {author_fqid}")


def get_response_image_content_type(base64_image_data):
    if base64_image_data.startswith("/9j/"):
        return "image/jpeg"
    elif base64_image_data.startswith("iVBORw0KGgo"):
        return "image/png"
    else:
        # TODO: replace with content type with specific subtype.
        return "application/octet-stream"
