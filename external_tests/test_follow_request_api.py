import pytest
import requests
import uuid
from rest_framework import status
from authors.models import Follow, Author

# Pytest mark for all tests in this file
pytestmark = pytest.mark.django_db


class TestFollowRequestAPI:
    """
    Tests for sending Follow requests to an author's inbox.
    Endpoint: /api/authors/{AUTHOR_SERIAL}/inbox
    Method: POST
    """

    def _get_follow_payload(self, actor, object_author, base_url):
        """Helper to create a follow request payload."""
        actor_api_url = f"{base_url}/api/authors/{actor.serial}/"
        object_api_url = f"{base_url}/api/authors/{object_author.serial}/"

        return {
            "type": "follow",
            "summary": (
                f"{actor.display_name} wants to follow "
                f"{object_author.display_name}"
            ),
            "actor": {
                "type": "author",
                "id": actor_api_url,
                "host": base_url,
                "displayName": actor.display_name,
                "github": actor.github,
                "profileImage": actor.profile_image,
                "web": f"{base_url}/authors/{actor.serial}/",
            },
            "object": {
                "type": "author",
                "id": object_api_url,
                "host": base_url,
                "displayName": object_author.display_name,
                "github": object_author.github,
                "profileImage": object_author.profile_image,
                "web": f"{base_url}/authors/{object_author.serial}/",
            },
        }

    def test_successful_follow_request(
        self, live_server, created_authors, authenticated_session
    ):
        """
        Tests that an authenticated user can successfully send a follow request
        to another user's inbox.
        """
        actor = created_authors[0]
        object_author = created_authors[1]

        session = authenticated_session(actor)
        inbox_url = (
            f"{live_server.url}/api/authors/"
            f"{object_author.serial}/inbox/"
        )
        payload = self._get_follow_payload(
            actor, object_author, live_server.url)

        response = session.post(inbox_url, json=payload)

        assert response.status_code == status.HTTP_201_CREATED
        response_json = response.json()
        assert response_json['type'] == 'follow'
        assert response_json['actor']['id'].endswith(f'{actor.serial}/')
        assert response_json['object']['id'].endswith(
            f'{object_author.serial}/')

        # Verify in DB
        assert Follow.objects.filter(
            follower=actor,
            following=object_author,
            status=Follow.Status.PENDING).exists()

    def test_follow_unauthenticated(self, live_server, created_authors):
        """
        Tests that sending a follow request without authentication fails.
        """
        actor = created_authors[0]
        object_author = created_authors[1]

        inbox_url = (
            f"{live_server.url}/api/authors/"
            f"{object_author.serial}/inbox/"
        )
        payload = self._get_follow_payload(
            actor, object_author, live_server.url)

        response = requests.post(inbox_url, json=payload)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_follow_mismatched_actor(
        self, live_server, created_authors, authenticated_session
    ):
        """
        Tests that a request fails if the authenticated user does not match the
        actor in the payload.
        """
        authenticated_user = created_authors[0]
        object_author = created_authors[1]
        payload_actor = created_authors[2]  # Different from authenticated user

        session = authenticated_session(authenticated_user)
        inbox_url = (
            f"{live_server.url}/api/authors/"
            f"{object_author.serial}/inbox/"
        )
        # Payload actor is different from session user
        payload = self._get_follow_payload(
            payload_actor, object_author, live_server.url)

        response = session.post(inbox_url, json=payload)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_follow_mismatched_object(
        self, live_server, created_authors, authenticated_session
    ):
        """
        Tests that a request fails if the inbox owner does not match the object
        in the payload.
        """
        actor = created_authors[0]
        inbox_owner = created_authors[1]
        payload_object = created_authors[2]  # Different from inbox owner

        session = authenticated_session(actor)
        # URL is for inbox_owner's inbox
        inbox_url = (
            f"{live_server.url}/api/authors/"
            f"{inbox_owner.serial}/inbox/"
        )
        # Payload object is different
        payload = self._get_follow_payload(
            actor, payload_object, live_server.url)

        response = session.post(inbox_url, json=payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_follow_self(
            self,
            live_server,
            created_authors,
            authenticated_session):
        """
        Tests that a user cannot send a follow request to themselves.
        """
        user = created_authors[0]

        session = authenticated_session(user)
        inbox_url = f"{live_server.url}/api/authors/{user.serial}/inbox/"
        payload = self._get_follow_payload(user, user, live_server.url)

        response = session.post(inbox_url, json=payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_duplicate_follow_request(
        self, live_server, created_authors, authenticated_session
    ):
        """
        Tests that sending a follow request when one is already pending fails.
        """
        actor = created_authors[0]
        object_author = created_authors[1]

        session = authenticated_session(actor)
        inbox_url = (
            f"{live_server.url}/api/authors/"
            f"{object_author.serial}/inbox/"
        )
        payload = self._get_follow_payload(
            actor, object_author, live_server.url)

        # First request should succeed
        response1 = session.post(inbox_url, json=payload)
        assert response1.status_code == status.HTTP_201_CREATED

        # Second request should be idempotent (return existing request)
        response2 = session.post(inbox_url, json=payload)
        assert response2.status_code == status.HTTP_200_OK

    def test_follow_nonexistent_author_inbox(
        self, live_server, created_authors, authenticated_session
    ):
        """
        Tests that a request fails with 404 Not Found if the inbox author
        does not exist.
        """
        actor = created_authors[0]
        object_author = created_authors[1]

        # Generate a UUID that is guaranteed not to exist in the database.
        non_existent_serial = str(uuid.uuid4())
        while Author.objects.filter(serial=non_existent_serial).exists():
            non_existent_serial = str(uuid.uuid4())

        session = authenticated_session(actor)
        # Use a non-existent serial for the inbox URL
        inbox_url = (
            f"{live_server.url}/api/authors/"
            f"{non_existent_serial}/inbox/"
        )
        payload = self._get_follow_payload(
            actor, object_author, live_server.url)

        response = session.post(inbox_url, json=payload)
        assert response.status_code == status.HTTP_404_NOT_FOUND
