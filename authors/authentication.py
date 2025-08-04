from django.contrib.auth.hashers import check_password
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import RemoteNode


class RemoteNodeAuthentication(BasicAuthentication):
    """
    Custom authentication class for remote nodes.

    Authenticates incoming requests from other nodes using the credentials
    (incoming_username, incoming_password) stored in the RemoteNode model.
    """

    def authenticate_credentials(self, userid, password, request=None):
        """
        Authenticate the userid and password against a RemoteNode.
        If no matching remote node is found, return None to allow other
        authentication methods to try.
        """
        try:
            # Find an active remote node with the given incoming username.
            node = RemoteNode.objects.get(
                incoming_username=userid, is_active=True)
        except RemoteNode.DoesNotExist:
            # No remote node found - let other auth methods try
            return None

        # Check if a password is set for incoming connections.
        if not node.incoming_password:
            raise AuthenticationFailed(
                'Node does not have a password '
                'configured for incoming connections.'
            )

        # Securely check the provided password against the stored hash.
        if not check_password(password, node.incoming_password):
            raise AuthenticationFailed(
                'Invalid credentials. Password mismatch.')

        # On successful authentication, set request.user to the first
        # element of this tuple and request.auth to the second.
        # Here, the 'user' is the RemoteNode instance itself.
        return (node, None)
