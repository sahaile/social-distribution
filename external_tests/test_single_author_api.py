import pytest
import requests
from rest_framework import status
import uuid
import urllib.parse

# Pytest mark for all tests in this file
pytestmark = pytest.mark.django_db


class TestSingleAuthorAPI:
    """
    Tests for the /api/authors/{AUTHOR_SERIAL}/ endpoint.
    """

    def test_get_single_author(self, live_server, created_authors):
        """
        Tests GET /api/authors/{AUTHOR_SERIAL}/
        Should retrieve a single author's profile.
        """
        author = created_authors[0]
        url = f'{live_server.url}/api/authors/{author.serial}/'
        response = requests.get(url)

        assert response.status_code == status.HTTP_200_OK

        response_json = response.json()
        assert response_json['type'] == 'author'
        assert response_json['id'].endswith(f'/api/authors/{author.serial}/')
        assert response_json['displayName'] == author.display_name
        assert response_json['github'] == author.github

    def test_get_nonexistent_author(self, live_server, db):
        """
        Tests GET /api/authors/{AUTHOR_SERIAL}/
        for an author that does not exist.
        Should return 404 Not Found.
        """
        from authors.models import Author

        non_existent_uuid = uuid.uuid4()
        # Ensure the generated UUID does not already exist in the database,
        # making the test robust against infinitesimal chances of collision.
        while Author.objects.filter(serial=non_existent_uuid).exists():
            non_existent_uuid = uuid.uuid4()

        url = f'{live_server.url}/api/authors/{non_existent_uuid}/'
        response = requests.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_author_unauthorized(self, live_server, created_authors):
        """
        Tests PUT /api/authors/{AUTHOR_SERIAL}/ without authentication.
        Should return 401 Unauthorized.
        """
        author = created_authors[0]
        url = f'{live_server.url}/api/authors/{author.serial}/'
        data = {'displayName': 'New Name'}
        response = requests.put(url, json=data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_update_author_wrong_user(
            self,
            live_server,
            created_authors,
            authenticated_session,
            auth_method):
        """
        Tests PUT /api/authors/{AUTHOR_SERIAL}/ as an authenticated user who is
        not the author being updated.
        Should return 403 Forbidden, for both Basic and Cookie auth.
        """
        author_to_update = created_authors[0]
        wrong_user = created_authors[1]

        # A PUT requires all fields to be sent.
        update_url = (
            f'{live_server.url}/api/authors/{author_to_update.serial}/'
        )
        update_data = {
            'displayName': 'New Name From Wrong User',
            'github': author_to_update.github or '',
            'profileImage': author_to_update.profile_image or ''
        }

        if auth_method == 'basic':
            response = requests.put(
                update_url,
                json=update_data,
                auth=(wrong_user.username, 'password123')
            )
        else:  # cookie
            session = authenticated_session(wrong_user)
            response = session.put(
                update_url,
                json=update_data
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize(
        "payload,test_id",
        [
            (
                {  # Invalid field value
                    'displayName': 'Test User 1',
                    'github': 'not-a-valid-url',
                    'profileImage': ''
                },
                "invalid_field_value"
            ),
            (
                {  # Missing 'profileImage'
                    'displayName': 'New Name',
                    'github': 'http://github.com/new-name'
                },
                "missing_field"
            ),
            (
                {  # Misspelled 'displayName'
                    'display_name': 'New Name',
                    'github': 'http://github.com/new-name',
                    'profileImage': ''
                },
                "misspelled_field"
            )
        ]
    )
    def test_update_author_with_bad_payloads(
            self, live_server, created_authors, payload, test_id):
        """
        Tests that PUT /api/authors/{AUTHOR_SERIAL}/
        fails with a 400 Bad Request
        for various invalid payloads:
        - A field has an invalid value (e.g., malformed URL).
        - A required field is missing.
        - A field name is misspelled (which is a form of missing field).
        """
        author = created_authors[0]

        update_url = f'{live_server.url}/api/authors/{author.serial}/'

        response = requests.put(
            update_url,
            json=payload,
            auth=(author.username, 'password123')
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_patch_author_correctly(
            self,
            live_server,
            created_authors,
            authenticated_session,
            auth_method):
        """
        Tests PATCH /api/authors/{AUTHOR_SERIAL}/
        to partially update an author.
        Should succeed and only update the specified field,
        using both Basic and Cookie authentication.
        """
        author = created_authors[0]
        original_github = author.github

        update_url = f'{live_server.url}/api/authors/{author.serial}/'
        new_name = f'New Patched Name via {auth_method}'
        patch_data = {'displayName': new_name}

        if auth_method == 'basic':
            response = requests.patch(
                update_url,
                json=patch_data,
                auth=(author.username, 'password123')
            )
        else:  # cookie
            session = authenticated_session(author)
            response = session.patch(
                update_url,
                json=patch_data
            )

        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json['displayName'] == new_name
        # Should be unchanged
        assert response_json['github'] == original_github

        # Verify with a subsequent GET request that the change persisted
        get_response = requests.get(update_url)
        assert get_response.status_code == status.HTTP_200_OK
        get_json = get_response.json()
        assert get_json['displayName'] == new_name

    def test_get_local_author_by_fqid(self, live_server, created_authors):
        """
        Tests GET /api/authors/{AUTHOR_FQID}/ for a local author by FQID.
        """
        local_author = created_authors[0]
        # The FQID points to the live server itself
        author_fqid = f'{live_server.url}/authors/{local_author.serial}/'
        encoded_fqid = urllib.parse.quote(author_fqid, safe='')

        url = f'{live_server.url}/api/authors/{encoded_fqid}/'
        response = requests.get(url)

        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()

        # The 'id' in the response body should be the author's API URL
        author_api_url = (
            f'{live_server.url}/api/authors/{local_author.serial}/'
        )
        assert response_json['id'] == author_api_url
        assert response_json['displayName'] == local_author.display_name

    def test_get_remote_author_proxy_success(self, live_server, remote_server):
        """
        Tests that the endpoint can successfully proxy a request for a
        remote author.
        """
        remote_host, remote_handler = remote_server
        remote_author_id = uuid.uuid4()

        remote_author_url = f'{remote_host}/authors/{remote_author_id}/'
        # The ID in the remote author's body should be their API URL
        remote_api_url = f'{remote_host}/api/authors/{remote_author_id}/'

        # Configure the remote server to return a valid author profile
        mock_profile = {
            "type": "author",
            "id": remote_api_url,
            "host": remote_host,
            "displayName": "Remote Author",
            "github": "http://github.com/remote",
            "profileImage": ""
        }
        remote_handler.set_response(mock_profile, status_code=200)

        # Make the request to our server
        encoded_fqid = urllib.parse.quote(remote_author_url, safe='')
        url = f'{live_server.url}/api/authors/{encoded_fqid}/'
        response = requests.get(url)

        # Assert that our server proxied the request and returned the result
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json['displayName'] == "Remote Author"
        assert response_json['host'] == remote_host
        # The ID in the response from our server should also be the API URL
        assert response_json['id'] == remote_api_url

    def test_get_remote_author_proxy_failure(self, live_server, remote_server):
        """
        Tests that the endpoint returns a 502 Bad Gateway if the remote
        server returns an error.
        """
        remote_host, remote_handler = remote_server
        remote_author_id = uuid.uuid4()
        remote_author_url = f'{remote_host}/authors/{remote_author_id}/'

        # Configure the remote server to return an error
        remote_handler.set_error_response(status_code=500)

        # Make the request to our server
        encoded_fqid = urllib.parse.quote(remote_author_url, safe='')
        url = f'{live_server.url}/api/authors/{encoded_fqid}/'
        response = requests.get(url)

        # Assert that our server returns a 502 Bad Gateway
        assert response.status_code == status.HTTP_502_BAD_GATEWAY

    def test_get_remote_author_proxy_invalid_format(
            self, live_server, remote_server):
        """
        Tests that the endpoint returns a 502 Bad Gateway if the remote
        server returns a 200 OK but with an invalid author format.
        """
        remote_host, remote_handler = remote_server
        remote_author_id = uuid.uuid4()
        remote_author_url = f'{remote_host}/authors/{remote_author_id}/'

        # Configure the remote server to return a badly formed author object
        mock_profile = {
            "displayName": "Remote Author With Bad Data",
        }
        remote_handler.set_response(mock_profile, status_code=200)

        # Make the request to our server
        encoded_fqid = urllib.parse.quote(remote_author_url, safe='')
        url = f'{live_server.url}/api/authors/{encoded_fqid}/'
        response = requests.get(url)

        # Assert that our server returns a 502 Bad Gateway because it
        # received a response it couldn't process.
        assert response.status_code == status.HTTP_502_BAD_GATEWAY
