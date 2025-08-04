import pytest
import urllib.parse
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework import status
from .factories import AuthorFactory
from entries.tests.factories import EntryFactory
from .factories import FollowFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    """API client for making requests"""
    return APIClient()


@pytest.fixture
def author_a():
    """Create a test author"""
    return AuthorFactory()


@pytest.fixture
def author_b():
    """Create another test author"""
    return AuthorFactory()


@pytest.fixture
def author_c():
    """Create a third test author"""
    return AuthorFactory()


class TestAuthorCommentedAPI:
    """Tests for /api/authors/{AUTHOR_SERIAL}/commented endpoints"""

    def test_get_author_commented_list_empty(self, api_client, author_a):
        """Test getting author's comments when they
        haven't commented on anything"""
        url = f'/api/authors/{author_a.serial}/commented/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comments'
        assert 'src' in response.data
        assert len(response.data['src']) == 0

    def test_get_author_commented_list_with_data(
            self, api_client, author_a, author_b):
        """Test getting author's comments list with data"""
        # Create entries by different authors
        entry1 = EntryFactory(author=author_b, visibility='PUBLIC')
        entry2 = EntryFactory(author=author_b, visibility='UNLISTED')

        # Author A comments on both entries via inbox
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'

        # Comment on first entry
        comment_data1 = {
            'type': 'comment',
            'comment': 'First comment by author A',
            'contentType': 'text/plain',
            'entry': entry1.get_api_url()
        }
        api_client.post(inbox_url, comment_data1, format='json')

        # Comment on second entry
        comment_data2 = {
            'type': 'comment',
            'comment': 'Second comment by author A',
            'contentType': 'text/markdown',
            'entry': entry2.get_api_url()
        }
        api_client.post(inbox_url, comment_data2, format='json')

        # Test getting author A's comments
        url = f'/api/authors/{author_a.serial}/commented/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comments'
        assert response.data['count'] == 2
        assert len(response.data['src']) == 2

        # Verify comment data
        comments = response.data['src']
        comment_texts = [c['comment'] for c in comments]
        assert 'First comment by author A' in comment_texts
        assert 'Second comment by author A' in comment_texts

        # Verify all comments are by author A
        for comment in comments:
            assert comment['author']['id'].endswith(
                f'/api/authors/{author_a.serial}/'
            )

    def test_get_author_commented_list_local_authentication(
            self, api_client, author_a, author_b):
        """Test that authenticated local users can
        see all comments by an author if they have permission."""
        # Create both public and friends-only entries
        public_entry = EntryFactory(author=author_b, visibility='PUBLIC')
        friends_entry = EntryFactory(author=author_b, visibility='FRIENDS')

        # Make A and B friends so A can comment on the friends-only entry
        FollowFactory.create_friendship(author1=author_a, author2=author_b)

        # Author A comments on both
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'

        # Comment on public entry
        api_client.post(inbox_url, {
            'type': 'comment',
            'comment': 'Comment on public entry',
            'entry': public_entry.get_api_url()
        }, format='json')

        # Comment on friends-only entry
        api_client.post(inbox_url, {
            'type': 'comment',
            'comment': 'Comment on friends entry',
            'entry': friends_entry.get_api_url()
        }, format='json')

        # Local authenticated user should see both comments
        url = f'/api/authors/{author_a.serial}/commented/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 2

    def test_get_author_commented_list_remote_only_public_unlisted(
            self, api_client, author_a, author_b):
        """Test that remote requests only see comments
        on public/unlisted entries"""
        # This test simulates remote access by not authenticating
        # In real implementation, this would be determined by HTTP Basic Auth

        # Create entries with different visibility
        public_entry = EntryFactory(author=author_b, visibility='PUBLIC')
        unlisted_entry = EntryFactory(author=author_b, visibility='UNLISTED')
        friends_entry = EntryFactory(author=author_b, visibility='FRIENDS')

        # Author A comments on all entries
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'

        for entry, comment_text in [
            (public_entry, 'Comment on public'),
            (unlisted_entry, 'Comment on unlisted'),
            (friends_entry, 'Comment on friends')
        ]:
            api_client.post(inbox_url, {
                'type': 'comment',
                'comment': comment_text,
                'entry': entry.get_api_url()
            }, format='json')

        # Unauthenticated (simulating remote) should only see public/unlisted
        api_client.force_authenticate(user=None)
        url = f'/api/authors/{author_a.serial}/commented/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        # Should only see comments on public and unlisted entries
        assert response.data['count'] == 2

        comment_texts = [c['comment'] for c in response.data['src']]
        assert 'Comment on public' in comment_texts
        assert 'Comment on unlisted' in comment_texts
        assert 'Comment on friends' not in comment_texts

    def test_get_author_commented_pagination(
            self, api_client, author_a, author_b):
        """Test pagination for author's comments"""
        # Create multiple entries and comments
        entries = [
            EntryFactory(
                author=author_b,
                visibility='PUBLIC') for _ in range(10)]

        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'

        # Create 10 comments
        for i, entry in enumerate(entries):
            api_client.post(inbox_url, {
                'type': 'comment',
                'comment': f'Comment {i + 1}',
                'entry': entry.get_api_url()
            }, format='json')

        # Test pagination
        url = f'/api/authors/{author_a.serial}/commented/?page=1&size=5'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 10
        assert response.data['page'] == 1
        assert response.data['size'] == 5
        assert len(response.data['src']) == 5

    def test_get_single_comment_by_author_and_serial(
            self, api_client, author_a, author_b):
        """Test GET /api/authors/{AUTHOR_SERIAL}/commented/{COMMENT_SERIAL}"""
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Create a comment
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        comment_response = api_client.post(inbox_url, {
            'type': 'comment',
            'comment': 'Specific comment to retrieve',
            'entry': entry.get_api_url()
        }, format='json')

        # Extract comment serial from response ID
        comment_id = comment_response.data['id']
        comment_serial = comment_id.split('/')[-1]

        # Test retrieving specific comment
        url = f'/api/authors/{author_a.serial}/commented/{comment_serial}/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comment'
        assert response.data['comment'] == 'Specific comment to retrieve'
        assert response.data['author']['id'].endswith(
            f'/api/authors/{author_a.serial}/'
        )

    def test_get_single_comment_not_found(self, api_client, author_a):
        """Test getting non-existent comment returns 404"""
        fake_comment_serial = "00000000-0000-0000-0000-000000000000"
        url = (
            f'/api/authors/{author_a.serial}/commented/'
            f'{fake_comment_serial}/'
        )

        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_author_commented_list_by_fqid(
            self, api_client, author_a, author_b):
        """Test GET /api/authors/{AUTHOR_FQID}/commented/ for FQID access"""
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Author A comments on the entry
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        api_client.post(inbox_url, {
            'type': 'comment',
            'comment': 'A test comment',
            'contentType': 'text/plain',
            'entry': entry.get_api_url()
        }, format='json')

        # Test FQID-based access
        factory = APIRequestFactory()
        request = factory.get('/')
        author_fqid = author_a.get_api_url(request=request)
        encoded_fqid = urllib.parse.quote(author_fqid, safe='')
        url = f'/api/authors/{encoded_fqid}/commented/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comments'
        assert len(response.data['src']) == 1
        assert response.data['src'][0]['author']['id'].endswith(
            f'/api/authors/{author_a.serial}/'
        )


class TestAuthorLikedAPI:
    """Tests for /api/authors/{AUTHOR_SERIAL}/liked endpoints"""

    def test_get_author_liked_list_empty(self, api_client, author_a):
        """Test getting author's likes when they haven't liked anything"""
        url = f'/api/authors/{author_a.serial}/liked/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'likes'
        assert 'src' in response.data
        assert len(response.data['src']) == 0

    def test_get_author_liked_list_with_data(
            self, api_client, author_a, author_b):
        """Test getting author's likes list with data"""
        # Create entries by different authors
        entry1 = EntryFactory(author=author_b, visibility='PUBLIC')
        entry2 = EntryFactory(author=author_b, visibility='UNLISTED')

        # Author A likes both entries via inbox
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'

        # Like first entry
        api_client.post(inbox_url, {
            'type': 'like',
            'object': entry1.get_api_url()
        }, format='json')

        # Like second entry
        api_client.post(inbox_url, {
            'type': 'like',
            'object': entry2.get_api_url()
        }, format='json')

        # Test getting author A's likes
        url = f'/api/authors/{author_a.serial}/liked/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'likes'
        assert response.data['count'] == 2
        assert len(response.data['src']) == 2

        # Verify like data
        likes = response.data['src']
        liked_objects = [like['object'] for like in likes]
        assert entry1.get_api_url() in liked_objects
        assert entry2.get_api_url() in liked_objects

        # Verify all likes are by author A
        for like in likes:
            assert like['author']['id'].endswith(
                f'/api/authors/{author_a.serial}/'
            )

    def test_get_author_liked_list_includes_comment_likes(
            self, api_client, author_a, author_b, author_c):
        """Test that author's liked list includes
        likes on both entries and comments"""
        # Create entry and comment
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Author B comments on their own entry
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        comment_response = api_client.post(inbox_url, {
            'type': 'comment',
            'comment': 'Author B commenting',
            'entry': entry.get_api_url()
        }, format='json')

        # Author A likes both the entry and the comment
        api_client.force_authenticate(user=author_a)

        # Like the entry
        api_client.post(inbox_url, {
            'type': 'like',
            'object': entry.get_api_url()
        }, format='json')

        # Like the comment
        comment_id = comment_response.data['id']
        api_client.post(inbox_url, {
            'type': 'like',
            'object': comment_id
        }, format='json')

        # Test getting author A's likes
        url = f'/api/authors/{author_a.serial}/liked/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 2

        liked_objects = [like['object'] for like in response.data['src']]
        assert entry.get_api_url() in liked_objects
        assert comment_id in liked_objects

    def test_get_author_liked_pagination(self, api_client, author_a, author_b):
        """Test pagination for author's likes"""
        # Create multiple entries and like them
        entries = [
            EntryFactory(
                author=author_b,
                visibility='PUBLIC') for _ in range(10)]

        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'

        # Like all entries
        for entry in entries:
            api_client.post(inbox_url, {
                'type': 'like',
                'object': entry.get_api_url()
            }, format='json')

        # Test pagination
        url = f'/api/authors/{author_a.serial}/liked/?page=1&size=5'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 10
        assert response.data['page'] == 1
        assert response.data['size'] == 5
        assert len(response.data['src']) == 5

    def test_get_single_like_by_author_and_serial(
            self, api_client, author_a, author_b):
        """Test GET /api/authors/{AUTHOR_SERIAL}/liked/{LIKE_SERIAL}"""
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Create a like
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        like_response = api_client.post(inbox_url, {
            'type': 'like',
            'object': entry.get_api_url()
        }, format='json')

        # Extract like serial from response ID
        like_id = like_response.data['id']
        like_serial = like_id.split('/')[-1]

        # Test retrieving specific like
        url = f'/api/authors/{author_a.serial}/liked/{like_serial}/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'like'
        assert response.data['object'] == entry.get_api_url()
        assert response.data['author']['id'].endswith(
            f'/api/authors/{author_a.serial}/'
        )

    def test_get_single_like_not_found(self, api_client, author_a):
        """Test getting non-existent like returns 404"""
        fake_like_serial = "00000000-0000-0000-0000-000000000000"
        url = f'/api/authors/{author_a.serial}/liked/{fake_like_serial}/'

        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_author_liked_by_fqid(self, api_client, author_a, author_b):
        """Test GET /api/authors/{AUTHOR_FQID}/liked for FQID access"""
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Author A likes the entry
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        api_client.post(inbox_url, {
            'type': 'like',
            'object': entry.get_api_url()
        }, format='json')

        # Test FQID-based access
        factory = APIRequestFactory()
        request = factory.get('/')
        author_fqid = author_a.get_api_url(request=request)
        encoded_fqid = urllib.parse.quote(author_fqid, safe='')
        url = f'/api/authors/{encoded_fqid}/liked/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'likes'
        assert len(response.data['src']) > 0
        assert response.data['src'][0]['author']['id'].endswith(
            f'/api/authors/{author_a.serial}/'
        )
        assert response.data['src'][0]['object'] == entry.get_api_url()


class TestCommentedLikedFQIDEndpoints:
    """Tests for FQID-based commented and liked endpoints"""

    def test_get_commented_by_fqid(self, api_client, author_a, author_b):
        """Test GET /api/commented/{COMMENT_FQID}"""
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Create a comment
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        comment_response = api_client.post(inbox_url, {
            'type': 'comment',
            'comment': 'Comment to retrieve by FQID',
            'entry': entry.get_api_url()
        }, format='json')

        # Test FQID-based comment access
        comment_fqid = comment_response.data['id']
        encoded_fqid = urllib.parse.quote(comment_fqid, safe='')
        url = f'/api/commented/{encoded_fqid}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comment'
        assert response.data['comment'] == 'Comment to retrieve by FQID'
        assert response.data['id'] == comment_fqid

    def test_get_liked_by_fqid(self, api_client, author_a, author_b):
        """Test GET /api/liked/{LIKE_FQID}"""
        entry = EntryFactory(author=author_b, visibility='PUBLIC')

        # Create a like
        api_client.force_authenticate(user=author_a)
        inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        like_response = api_client.post(inbox_url, {
            'type': 'like',
            'object': entry.get_api_url()
        }, format='json')

        # Test FQID-based like access
        like_fqid = like_response.data['id']
        encoded_fqid = urllib.parse.quote(like_fqid, safe='')
        url = f'/api/liked/{encoded_fqid}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'like'
        assert response.data['object'] == entry.get_api_url()
        assert response.data['id'] == like_fqid
