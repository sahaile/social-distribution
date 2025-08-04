import pytest
import requests
from rest_framework import status
from unittest.mock import patch

pytestmark = pytest.mark.django_db


class TestEntriesAPI:
    """
    Tests for the /api/entries/ endpoint.
    """

    def test_get_public_entry(self, live_server, created_entries):
        """
        Tests GET /api/authors/{author_id}/entries/{entry_id}
        Should return a single entry by ID.
        """
        for entry in created_entries:
            if entry.visibility == 'PUBLIC':
                url = (
                    f'{live_server.url}/api/authors/'
                    f'{entry.author.serial}/entries/{entry.serial}/'
                )
                response = requests.get(url)

                assert response.status_code == status.HTTP_200_OK
                response_json = response.json()
                assert response_json['type'] == 'entry'
                assert response_json['id'] == entry.url
                assert response_json['title'] == entry.title
                assert response_json['description'] == entry.description
                assert response_json['content'] == entry.content

    @patch('authors.services.NodeService.send_to_inbox')
    def test_create_public_entry(
            self,
            mock_send_to_inbox,
            live_server,
            remote_authors,
            created_authors,
            authenticated_session):
        from authors.models import Follow

        new_entry_author = created_authors[0]
        remote_follower = remote_authors[0]

        # Create a follow relationship with a remote author
        Follow.objects.create(
            follower=remote_follower,
            following=new_entry_author,
            status=Follow.Status.ACCEPTED
        )

        session = authenticated_session(new_entry_author)

        # Create a new public entry via API
        base_url = f'{live_server.url}/api/authors/{new_entry_author.serial}'
        url = f'{base_url}/entries/'
        entry_data = {
            'title': 'Test Public Entry',
            'description': 'A test entry for checking inbox delivery',
            'content': 'This is test content',
            'contentType': 'text/plain',
            'visibility': 'PUBLIC'
        }

        response = session.post(url, json=entry_data)
        assert response.status_code == status.HTTP_201_CREATED

        # Verify the entry was created and sent to inbox
        mock_send_to_inbox.assert_called()
