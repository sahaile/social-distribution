from rest_framework.permissions import BasePermission, SAFE_METHODS
from urllib.parse import urlparse
from .models import RemoteNode


class IsAuthenticatedOrRemoteNodeOrReadOnly(BasePermission):
    """
    Custom permission to allow read-only access to anyone,
    but require authentication for write operations.
    Authentication can be from a local user or a remote node.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        # For write methods, require authentication.
        return bool(
            request.user and (
                (hasattr(
                    request.user,
                    'is_authenticated'
                ) and request.user.is_authenticated
                ) or isinstance(
                    request.user,
                    RemoteNode)))


class IsAuthenticatedOrReadOnlyForPublic(BasePermission):
    """
    Allow read access to public content without authentication,
    but require authentication for write operations.
    Authentication can be from a local user or a remote node.
    """

    def has_permission(self, request, view):
        # Allow GET requests without authentication
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True

        # Require authentication for POST, PUT, DELETE
        # Check for both local user authentication and remote node
        # authentication
        return bool(
            request.user and (
                (hasattr(
                    request.user,
                    'is_authenticated'
                ) and request.user.is_authenticated
                ) or isinstance(
                    request.user,
                    RemoteNode)))

    def has_object_permission(self, request, view, obj):
        # Allow GET requests without authentication
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True

        # For write operations, check authentication first
        is_authenticated = bool(
            request.user and (
                (hasattr(
                    request.user,
                    'is_authenticated'
                ) and request.user.is_authenticated
                ) or isinstance(
                    request.user,
                    RemoteNode)))

        if not is_authenticated:
            return False

        # For local users, check ownership
        if hasattr(
                request.user,
                'is_authenticated') and request.user.is_authenticated:
            # For Author objects, must be the same user
            if hasattr(obj, 'serial'):  # Author object
                return obj == request.user
            # For other objects, check the author field
            elif hasattr(obj, 'author'):
                return obj.author == request.user

        # For remote nodes, allow access (additional authorization handled in
        # view)
        elif isinstance(request.user, RemoteNode):
            return True

        return False


class IsRemoteNode(BasePermission):
    """
    Allows access only to authenticated remote nodes.
    """

    def has_permission(self, request, view):
        """
        Check if the request comes from an authenticated RemoteNode.
        """
        # The RemoteNodeAuthentication class attaches the node to request.user.
        # RemoteNode objects don't have is_authenticated attribute,
        # so we just check if it's a RemoteNode instance.
        return (request.user and isinstance(request.user, RemoteNode))


class IsAllowedToActAsAuthor(BasePermission):
    """
    Permission to ensure a remote node can only act on behalf of an author
    that belongs to its own host. This prevents a node from impersonating
    authors from other nodes.
    """
    message = (
        "You do not have permission to act on behalf of an author "
        "from a different host."
    )

    def has_permission(self, request, view):
        """
        Checks if the authenticated node's host matches the host of the
        author/actor in the request payload.
        """
        # This permission should only apply after
        # RemoteNodeAuthentication has run.
        # Check if request.user is an instance of our RemoteNode model.
        if not isinstance(request.user, RemoteNode):
            return False

        # The authenticated node making the request.
        authenticated_node = request.user

        # Find the author/actor data within the payload.
        # For a 'follow' object, the actor is at request.data['actor'].
        # For 'entry', 'comment', and 'like' objects, it is at
        # request.data['author'].
        payload = request.data
        actor_data = None
        if payload.get('type') == 'follow':
            actor_data = payload.get('actor')
        else:
            actor_data = payload.get('author')

        if not actor_data or not isinstance(
                actor_data, dict) or 'id' not in actor_data:
            # If the payload is malformed or doesn't specify an actor, deny.
            return False

        # Extract the host from the actor's FQID URL.
        try:
            actor_url = actor_data['id']
            parsed_url = urlparse(actor_url)
            # Reconstruct 'http://hostname/' from the parsed URL.
            actor_host = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        except (TypeError, AttributeError):
            # The 'id' was not a valid URL string.
            return False

        # Compare the host of the authenticated node with the host
        # from the payload.
        # Normalize by removing trailing slashes for a robust comparison.
        return authenticated_node.host.rstrip('/') == actor_host.rstrip('/')


class CanPostToInbox(BasePermission):
    """
    Custom permission for the InboxView.
    Allows a request if:
    1. It is from an authenticated RemoteNode and is
    allowed to act as the author.
    2. It is from a locally authenticated user.
    """

    def has_permission(self, request, view):
        # Case 1: Authenticated Remote Node
        if isinstance(request.user, RemoteNode):
            # If it's a remote node, delegate to IsAllowedToActAsAuthor
            return IsAllowedToActAsAuthor().has_permission(request, view)

        # Case 2: Locally Authenticated User
        if hasattr(
                request.user,
                'is_authenticated') and request.user.is_authenticated:
            # For local users, we just need to ensure they are logged in.
            # Further checks (like if they can comment on a post) happen inside
            # the view.
            return True

        return False


class IsAuthorOrReadOnly(BasePermission):
    """
    Custom permission to only allow authors of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in SAFE_METHODS:
            return True

        # Write permissions are only allowed to the author of the object.
        return obj.author == request.user
