from rest_framework.permissions import BasePermission, SAFE_METHODS
from django.shortcuts import get_object_or_404
from authors.models import Author
from .models import Entry


class EntryPermission(BasePermission):
    """
    Permissions for entries.
    - Authenticated users can create entries for themselves.
    - Authors can update/delete their own entries.
    - Read access is determined by entry visibility.
    """

    def has_permission(self, request, view):
        # Allow any safe method (GET, HEAD, OPTIONS) for listing,
        # the queryset will be filtered in the view itself.
        if request.method in SAFE_METHODS:
            return True

        # For POST (create), user must be authenticated and be the author
        # they are attempting to post for.
        author_serial = view.kwargs.get('author_serial')
        if not author_serial:
            return False  # Should not happen with correct URL config

        author = get_object_or_404(Author, serial=author_serial)
        return request.user.is_authenticated and request.user == author

    def has_object_permission(self, request, view, obj):
        # For safe methods (GET), check the entry's visibility.
        if request.method in SAFE_METHODS:
            # Public and unlisted entries are accessible to everyone
            if obj.visibility in ['PUBLIC', 'UNLISTED']:
                return True

            # For friends-only entries, check authentication and relationships
            if obj.visibility == 'FRIENDS':
                if not request.user.is_authenticated:
                    return False

                # Author can always see their own entries
                if obj.author == request.user:
                    return True

                # Friends can see friends-only entries
                return request.user.is_friend_with(obj.author)

            # Author can always see their own entries (any visibility)
            if request.user.is_authenticated and obj.author == request.user:
                return True

            return False

        # For unsafe methods (PUT, DELETE), the user must be the author
        return obj.author == request.user


class CanAccessContentPermission(BasePermission):
    """
    Permission to check if a user can access the parent content
    (e.g., an Entry when listing its comments).
    - Read access is determined by the parent content's visibility.
    """

    def has_permission(self, request, view):
        # This permission only cares about safe methods.
        # Write permissions for creating comments/likes are handled by the
        # Inbox.
        if request.method not in SAFE_METHODS:
            return True

        author_serial = view.kwargs.get('author_serial')
        entry_serial = view.kwargs.get('entry_serial')

        author = get_object_or_404(Author, serial=author_serial)
        entry = get_object_or_404(
            Entry, author=author, serial=entry_serial, is_deleted=False
        )

        # Re-use the logic from EntryPermission to check visibility
        entry_perm = EntryPermission()
        return entry_perm.has_object_permission(request, view, entry)


class FQIDBasedPermission(BasePermission):
    """
    Permission class for FQID-based endpoints.
    Assumes the view will handle FQID parsing and provide the entry object.
    This permission only checks visibility once the object exists.
    """

    def has_permission(self, request, view):
        # Allow all safe methods - object permission will be checked later
        if request.method in SAFE_METHODS:
            return True

        # For non-safe methods, require authentication
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Re-use the entry permission logic
        entry_perm = EntryPermission()
        return entry_perm.has_object_permission(request, view, obj)
