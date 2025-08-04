import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse

from .models import RemoteNode


class NodeService:
    """
    A service for interacting with remote nodes.
    Handles sending data to remote inboxes with proper authentication.
    """

    def send_to_inbox(self, recipient_author_url: str, data: dict):
        """
        Sends a payload to the inbox of a remote author.

        Args:
            recipient_author_url: The FQID (URL) of the recipient author.
            data: The JSON-serializable dictionary to send.

        Returns:
            A requests.Response object on success,
            or raises an exception on failure.
        """
        parsed_url = urlparse(recipient_author_url)
        remote_host = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        inbox_url = f"{recipient_author_url.rstrip('/')}/inbox/"

        try:
            node = RemoteNode.objects.get(host=remote_host, is_active=True)
        except RemoteNode.DoesNotExist:
            # If we don't know the node, or it's disabled, we can't send.
            return

        auth = HTTPBasicAuth(node.outgoing_username, node.outgoing_password)

        try:
            response = requests.post(
                inbox_url,
                json=data,
                auth=auth,
                headers={'Content-Type': 'application/json'},
                timeout=5  # 5-second timeout for the request
            )
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException:
            # Handle connection errors, timeouts, etc.
            raise
