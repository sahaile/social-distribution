import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework import status
import urllib.parse
from .factories import AuthorFactory

Author = get_user_model()


@pytest.fixture
def api_client():
    """API client for making requests"""
    return APIClient()


@pytest.fixture
def author():
    """Create a test author"""
    return AuthorFactory()


@pytest.fixture
def other_author():
    """Create another test author"""
    return AuthorFactory()


@pytest.mark.django_db
class TestAuthorsListAPI:
    """Test GET /api/authors/ endpoint"""

    def test_get_authors_list_empty(self, api_client):
        """Test getting authors list when no authors exist"""
        response = api_client.get('/api/authors/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'authors'
        assert response.data['authors'] == []

    def test_get_authors_list_with_data(self, api_client):
        """Test getting authors list with data"""
        # Create some authors
        AuthorFactory.create_batch(2)

        response = api_client.get('/api/authors/')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'authors'
        assert len(response.data['authors']) == 2

        # Check response format matches spec
        author_data = response.data['authors'][0]
        assert 'type' in author_data
        assert 'id' in author_data
        assert 'host' in author_data
        assert 'displayName' in author_data
        assert author_data['type'] == 'author'


@pytest.mark.django_db
class TestSingleAuthorAPI:
    """Test GET/PUT /api/authors/{serial_or_fqid}/ endpoint"""

    def test_get_author_by_uuid(self, api_client, author):
        """Test getting author by UUID serial"""
        url = f'/api/authors/{author.serial}/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'author'
        assert response.data['displayName'] == author.display_name
        assert response.data['id'].endswith(f'/api/authors/{author.serial}/')

    def test_get_author_by_fqid(self, api_client, author):
        """Test getting author by FQID (URL-encoded)"""
        # For a local FQID test, the author's host must match the
        # test client's host.
        author.host = 'http://testserver'
        author.save()

        # Create a mock request to generate the correct FQID for the
        # test environment.
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = author  # or some anonymous user

        # Generate the FQID using the mock request
        fqid = author.get_api_url(request=request)
        encoded_fqid = urllib.parse.quote(fqid, safe='')
        url = f'/api/authors/{encoded_fqid}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == fqid

    def test_update_own_author_profile(self, api_client, author):
        """Test updating own author profile (authenticated)"""
        api_client.force_authenticate(user=author)

        url = f'/api/authors/{author.serial}/'
        update_data = {
            'displayName': 'Updated Name',
            'github': 'http://github.com/updated',
            'host': author.host,
            'profileImage': author.profile_image,
        }

        response = api_client.put(url, update_data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['displayName'] == 'Updated Name'

        # Verify database was updated
        author.refresh_from_db()
        assert author.display_name == 'Updated Name'

    def test_update_other_author_profile_forbidden(
            self, api_client, author, other_author):
        """Test that you cannot update another author's profile"""
        api_client.force_authenticate(user=other_author)

        url = f'/api/authors/{author.serial}/'
        update_data = {
            'displayName': 'Hacked Name',
            'host': author.host,
        }

        response = api_client.put(url, update_data, format='json')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_update_without_authentication(self, api_client, author):
        """Test that update requires authentication"""
        url = f'/api/authors/{author.serial}/'
        update_data = {
            'displayName': 'Unauthorized Update',
            'host': author.host,
        }

        response = api_client.put(url, update_data, format='json')

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_nonexistent_author(self, api_client):
        """Test getting non-existent author returns 404"""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        url = f'/api/authors/{fake_uuid}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_author_not_found(self, api_client):
        """Test getting a non-existent author by serial"""
        fake_serial = "00000000-0000-0000-0000-000000000000"
        url = f'/api/authors/{fake_serial}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_fqid_fallback_extraction(self, api_client, author):
        """Test FQID fallback when direct lookup fails"""
        # Create a fake FQID that doesn't exist in the database as a full URL
        # but contains the author's serial at the end
        fake_fqid = f"http://othernode.com/api/authors/{author.serial}"
        encoded_fqid = urllib.parse.quote(fake_fqid, safe='')
        url = f'/api/authors/{encoded_fqid}/'

        response = api_client.get(url)

        # The request should fail with a 502 because the host is not reachable
        assert response.status_code == status.HTTP_502_BAD_GATEWAY


@pytest.mark.django_db
class TestAPIPermissions:
    """Test API permission system"""

    def test_unauthenticated_get_allowed(self, api_client, author):
        """Test that GET requests work without authentication"""
        url = f'/api/authors/{author.serial}/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

    def test_unauthenticated_list_allowed(self, api_client):
        """Test that GET /api/authors/ works without authentication"""
        AuthorFactory.create_batch(2)
        response = api_client.get('/api/authors/')

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['authors']) == 2
