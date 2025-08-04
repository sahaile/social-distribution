import pytest
import urllib.parse
from rest_framework.test import APIClient
from rest_framework import status
from authors.tests.factories import AuthorFactory, FollowFactory
from .factories import EntryFactory
import uuid

# Pytest mark for all tests in this file
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


class TestEntryAPI:
    """Tests for Entry CRUD and permissions"""

    def test_create_entry(self, api_client, author_a):
        """Authenticated author can create a public entry."""
        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'
        data = {
            'title': 'Test Entry',
            'description': 'A test entry.',
            'contentType': 'text/plain',
            'content': 'Hello world.',
            'visibility': 'PUBLIC'
        }
        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == 'Test Entry'

    def test_list_public_entries_unauthenticated(self, api_client, author_a):
        """Unauthenticated users can see public entries."""
        EntryFactory(author=author_a, visibility='PUBLIC')
        # This one should not be visible
        EntryFactory(author=author_a, visibility='FRIENDS')

        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'entries'
        assert response.data['count'] == 1
        assert len(response.data['src']) == 1
        assert response.data['src'][0]['visibility'] == 'PUBLIC'

    def test_update_other_author_entry_forbidden(
            self, api_client, author_a, author_b):
        """Author B cannot update Author A's entry."""
        entry = EntryFactory(author=author_a)
        api_client.force_authenticate(user=author_b)

        url = f'/api/authors/{author_a.serial}/entries/{entry.serial}/'
        data = {'title': 'Hacked Title'}
        response = api_client.put(url, data, format='json')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_soft_delete_entry(self, api_client, author_a):
        """Author can soft-delete their own entry."""
        entry = EntryFactory(author=author_a)
        api_client.force_authenticate(user=author_a)

        url = f'/api/authors/{author_a.serial}/entries/{entry.serial}/'
        response = api_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify the entry is gone from the list
        list_url = f'/api/authors/{author_a.serial}/entries/'
        list_response = api_client.get(list_url)
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data['count'] == 0
        assert len(list_response.data['src']) == 0


class TestInboxAPI:
    """Tests for posting comments and likes to the inbox"""

    def test_post_comment_to_inbox(self, api_client, author_a, author_b):
        """Author B can comment on Author A's entry via inbox."""
        entry = EntryFactory(author=author_a)
        api_client.force_authenticate(user=author_b)

        url = f'/api/authors/{author_a.serial}/inbox/'
        data = {
            'type': 'comment',
            'comment': 'This is a test comment.',
            'contentType': 'text/plain',
            'entry': entry.get_api_url()
        }

        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['comment'] == 'This is a test comment.'
        assert response.data['author']['id'].endswith(
            f'/api/authors/{author_b.serial}/')

    def test_post_like_to_inbox(self, api_client, author_a, author_b):
        """Author B can like Author A's entry via inbox."""
        entry = EntryFactory(author=author_a)
        api_client.force_authenticate(user=author_b)

        url = f'/api/authors/{author_a.serial}/inbox/'
        data = {
            'type': 'like',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'object': entry.get_api_url()
        }

        response = api_client.post(url, data, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['author']['id'].endswith(
            f'/api/authors/{author_b.serial}/')
        assert response.data['object'] == entry.get_api_url()

    def test_list_comments_and_likes(self, api_client, author_a, author_b):
        """Comments and likes appear on the entry's list endpoints."""
        entry = EntryFactory(author=author_a)

        # Author B posts a comment
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        api_client.post(inbox_url,
                        {'type': 'comment',
                         'comment': 'First!',
                         'entry': entry.get_api_url()},
                        format='json')

        # Author B posts a like
        api_client.post(inbox_url, {
            'type': 'like',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'object': entry.get_api_url()
        }, format='json')

        # Unauthenticate to check public read access
        api_client.force_authenticate(user=None)

        # Check comments list
        comments_url = (
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/comments/'
        )
        comments_response = api_client.get(comments_url)
        assert comments_response.status_code == status.HTTP_200_OK
        assert comments_response.data['type'] == 'comments'
        assert comments_response.data['count'] == 1
        assert comments_response.data['src'][0]['comment'] == 'First!'

        # Check likes list
        likes_url = (
            f'/api/authors/{author_a.serial}/entries/'
            f'{entry.serial}/likes/'
        )
        likes_response = api_client.get(likes_url)
        assert likes_response.status_code == status.HTTP_200_OK
        assert likes_response.data['type'] == 'likes'
        assert likes_response.data['count'] == 1
        assert likes_response.data['src'][0]['author']['id'].endswith(
            f'/api/authors/{author_b.serial}/')

    def test_list_paginated_comments_and_likes(
            self, api_client, author_a, author_b):
        """Comments/likes list endpoints should
        return paginated wrapper object"""
        entry = EntryFactory(author=author_a)

        # Author B posts a comment and a like
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'comment': 'A comment',
            'entry': entry.get_api_url()
        }
        api_client.post(inbox_url, comment_data, format='json')

        like_data = {
            'type': 'like',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'object': entry.get_api_url()
        }
        api_client.post(inbox_url, like_data, format='json')

        # Unauthenticate to check public read access
        api_client.force_authenticate(user=None)

        # Check comments list response structure
        comments_url = (
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/comments/'
        )
        comments_response = api_client.get(comments_url)
        assert comments_response.status_code == status.HTTP_200_OK
        assert comments_response.data['type'] == 'comments'
        assert 'count' in comments_response.data
        assert 'src' in comments_response.data

        # Check likes list response structure
        likes_url = (
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/likes/'
        )
        likes_response = api_client.get(likes_url)
        assert likes_response.status_code == status.HTTP_200_OK
        assert likes_response.data['type'] == 'likes'
        assert 'count' in likes_response.data
        assert 'src' in likes_response.data


class TestLikesOnCommentAPI:
    """Tests for listing likes on a comment."""

    def test_list_likes_on_comment(
            self,
            api_client,
            author_a,
            author_b,
            author_c):
        """
        Tests GET /api/authors/{A}/entries/{E}/comments/{C}/likes/
        """
        # Author A creates an entry
        entry = EntryFactory(author=author_a)
        # Author B comments on it
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_res = api_client.post(inbox_url, {
            'type': 'comment',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'comment': 'A comment to be liked',
            'contentType': 'text/plain',
            'entry': entry.get_api_url()
        }, format='json')
        comment_id = comment_res.data['id']
        comment_serial = comment_id.split('/')[-1]

        # Author C likes the comment. The like should be sent to the COMMENT's
        # author's inbox (author_b), not the entry's author's inbox.
        api_client.force_authenticate(user=author_c)
        like_inbox_url = f'/api/authors/{author_b.serial}/inbox/'
        api_client.post(like_inbox_url, {
            'type': 'like',
            'author': {
                'id': author_c.get_api_url(),
                'displayName': author_c.display_name,
                'host': author_c.host
            },
            'object': comment_id
        }, format='json')

        # Check the likes list for that comment
        api_client.force_authenticate(
            user=None)  # check unauthenticated access
        likes_url = f'/api/authors/{
            author_a.serial}/entries/{
            entry.serial}/comments/{comment_serial}/likes/'
        response = api_client.get(likes_url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'likes'
        assert response.data['count'] == 1
        assert (response.data['src'][0]['author']['id']
                .endswith(f"/api/authors/{author_c.serial}/"))

    def test_post_like_to_comment(
            self,
            api_client,
            author_a,
            author_b,
            author_c):
        """
        Tests that an authenticated user can like a comment via
        POST /.../entries/{E}/comments/{C}/likes/
        """
        entry = EntryFactory(author=author_a)

        # Author B posts a comment
        api_client.force_authenticate(user=author_b)
        comment_res = api_client.post(
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/comments/',
            {'comment': 'A comment to be liked', 'contentType': 'text/plain'},
            format='json'
        )
        assert comment_res.status_code == status.HTTP_201_CREATED
        comment_serial = comment_res.data['serial']

        # Author C likes Author B's comment
        api_client.force_authenticate(user=author_c)
        url = (f'/api/authors/{author_a.serial}/entries/'
               f'{entry.serial}/comments/{comment_serial}/likes/')
        response = api_client.post(url, {}, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['type'] == 'like'
        assert response.data['author']['id'].endswith(
            f"/api/authors/{author_c.serial}/")

        # Get the comment object and check for the like using its URL
        from entries.models import Like, Comment
        comment = Comment.objects.get(serial=comment_serial)
        assert Like.objects.filter(
            author=author_c, object_id=comment.url).exists()

    def test_get_likes_by_comment_fqid(self, api_client, author_a, author_b):
        """Test GET /api/entries/{ENTRY_FQID}/comments"""
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Create a comment via inbox
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'comment': 'Test comment via FQID',
            'contentType': 'text/plain',
            'entry': entry.get_api_url()
        }
        api_client.post(inbox_url, comment_data, format='json')

        # Test FQID-based comments endpoint
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/comments/'

        api_client.force_authenticate(user=None)  # Test unauthenticated access
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comments'
        assert response.data['count'] == 1
        assert response.data['src'][0]['comment'] == 'Test comment via FQID'
        assert response.data['id'] == f"{entry_fqid}/comments"

    def test_post_duplicate_like_to_comment(
            self, api_client, author_a, author_b, author_c):
        """
        Tests that liking a comment twice results in a 400 Conflict error.
        """
        entry = EntryFactory(author=author_a)
        # Author B posts a comment
        api_client.force_authenticate(user=author_b)
        comment_res = api_client.post(
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/comments/',
            {'comment': 'A comment to be liked', 'contentType': 'text/plain'},
            format='json'
        )
        assert comment_res.status_code == status.HTTP_201_CREATED
        comment_serial = comment_res.data['serial']

        # Author C likes the comment once (should succeed)
        api_client.force_authenticate(user=author_c)
        likes_url = f'/api/authors/{
            author_a.serial}/entries/{
            entry.serial}/comments/{comment_serial}/likes/'
        first_like_response = api_client.post(likes_url, {}, format='json')
        assert first_like_response.status_code == status.HTTP_201_CREATED

        # Author C tries to like it again (should fail with 400)
        second_like_response = api_client.post(likes_url, {}, format='json')
        assert second_like_response.status_code == status.HTTP_400_BAD_REQUEST
        assert second_like_response.data[0].code == 'conflict'


class TestFriendsOnlyVisibility:
    """Tests for friends-only entry visibility logic"""

    def test_friends_can_see_friends_only_entries(
            self, api_client, author_a, author_b):
        """Friends can see each other's friends-only entries."""
        # Create mutual friendship between author_a and author_b
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        # Author A creates a friends-only entry
        EntryFactory(
            author=author_a,
            visibility='FRIENDS',
            title='Friends Only Post')
        EntryFactory(
            author=author_a,
            visibility='PUBLIC',
            title='Public Post')

        # Author B (friend) should see both entries
        api_client.force_authenticate(user=author_b)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 2
        titles = [entry['title'] for entry in response.data['src']]
        assert 'Friends Only Post' in titles
        assert 'Public Post' in titles

    def test_non_friends_cannot_see_friends_only_entries(
            self, api_client, author_a, author_b):
        """Non-friends cannot see friends-only entries."""
        # Author A creates a friends-only entry (no friendship exists)
        EntryFactory(
            author=author_a,
            visibility='FRIENDS',
            title='Secret Friends Post')
        EntryFactory(author=author_a, visibility='PUBLIC', title='Public Post')

        # Author B (not friend) should only see public entry
        api_client.force_authenticate(user=author_b)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert response.data['src'][0]['title'] == 'Public Post'
        assert response.data['src'][0]['visibility'] == 'PUBLIC'

    def test_unauthenticated_cannot_see_friends_only_entries(
            self, api_client, author_a):
        """Unauthenticated users cannot see friends-only entries."""
        # Author A creates both types of entries
        EntryFactory(
            author=author_a,
            visibility='FRIENDS',
            title='Friends Only')
        EntryFactory(
            author=author_a,
            visibility='PUBLIC',
            title='Public Entry')

        # Unauthenticated request should only see public
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert response.data['src'][0]['title'] == 'Public Entry'

    def test_author_can_see_own_friends_only_entries(
            self, api_client, author_a):
        """Authors can always see their own entries
        regardless of visibility."""
        # Author A creates all types of entries
        EntryFactory(
            author=author_a,
            visibility='FRIENDS',
            title='My Friends Entry')
        EntryFactory(
            author=author_a,
            visibility='PUBLIC',
            title='My Public Entry')
        EntryFactory(
            author=author_a,
            visibility='UNLISTED',
            title='My Unlisted Entry')

        # Author A should see all their own entries
        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 3
        titles = [entry['title'] for entry in response.data['src']]
        assert 'My Friends Entry' in titles
        assert 'My Public Entry' in titles
        assert 'My Unlisted Entry' in titles

    def test_friends_only_entry_detail_access(
            self, api_client, author_a, author_b):
        """Test individual entry access for friends-only entries."""
        # Create friendship
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        # Author A creates friends-only entry
        friends_entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Friend can access individual entry
        api_client.force_authenticate(user=author_b)
        url = f'/api/authors/{author_a.serial}/entries/{friends_entry.serial}/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['visibility'] == 'FRIENDS'

        # Non-friend cannot access individual entry
        author_c = AuthorFactory()
        api_client.force_authenticate(user=author_c)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_story_friend_cannot_see_other_friends_comment(
            self, api_client, author_a, author_b, author_c):
        """
        US 7.4: Comments on friends-only entries are only visible to the
        entry's author and the comment's author.
        This test confirms that a friend of the entry owner cannot see a
        comment made by another, non-mutual friend.
        """
        # A is friends with B and C, but B and C are not friends
        FollowFactory.create_friendship(author1=author_a, author2=author_b)
        FollowFactory.create_friendship(author1=author_a, author2=author_c)

        # Author A creates a friends-only entry
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Author B comments on the entry directly
        api_client.force_authenticate(user=author_b)
        comments_url = (
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/comments/'
        )
        comment_data = {
            'comment': 'A secret comment from B',
            'contentType': 'text/plain'
        }
        post_response = api_client.post(
            comments_url, comment_data, format='json')
        assert post_response.status_code == status.HTTP_201_CREATED

        # As Author C (friend of A, but not B), view comments
        api_client.force_authenticate(user=author_c)
        response_c = api_client.get(comments_url)

        # C should NOT see B's comment, as per the current implementation
        assert response_c.status_code == status.HTTP_200_OK
        assert response_c.data['count'] == 0
        assert len(response_c.data['src']) == 0

        # As Author A (entry owner), view comments
        api_client.force_authenticate(user=author_a)
        response_a = api_client.get(comments_url)
        assert response_a.status_code == status.HTTP_200_OK
        assert response_a.data['count'] == 1
        assert (response_a.data['src'][0]['comment'] ==
                'A secret comment from B')


class TestFQIDEndpoints:
    """Tests for FQID-based API endpoints as required by spec"""

    def test_get_entry_by_fqid_public(self, api_client, author_a):
        """Test GET /api/entries/{ENTRY_FQID} for public entry"""
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # URL encode the FQID
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'entry'
        assert response.data['id'] == entry_fqid
        assert response.data['title'] == entry.title
        assert response.data['visibility'] == 'PUBLIC'

    def test_get_entry_by_fqid_friends_only_authenticated(
            self, api_client, author_a, author_b):
        """Test GET /api/entries/{ENTRY_FQID} for
        friends-only entry by friend"""
        # Create friendship
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # URL encode the FQID
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/'

        # Friend should be able to access
        api_client.force_authenticate(user=author_b)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['visibility'] == 'FRIENDS'

    def test_get_entry_by_fqid_friends_only_forbidden(
            self, api_client, author_a, author_b):
        """Test GET /api/entries/{ENTRY_FQID} for
        friends-only entry by non-friend"""
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # URL encode the FQID
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/'

        # Non-friend should be forbidden
        api_client.force_authenticate(user=author_b)
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_entry_by_fqid_not_found(self, api_client):
        """Test GET /api/entries/{ENTRY_FQID} for non-existent entry"""
        fake_fqid = (
            "http://example.com/api/authors/"
            "fake-uuid/entries/fake-entry-uuid"
        )
        encoded_fqid = urllib.parse.quote(fake_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_comments_by_entry_fqid(self, api_client, author_a, author_b):
        """Test GET /api/entries/{ENTRY_FQID}/comments"""
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Create a comment via inbox
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'comment': 'Test comment via FQID',
            'contentType': 'text/plain',
            'entry': entry.get_api_url()
        }
        api_client.post(inbox_url, comment_data, format='json')

        # Test FQID-based comments endpoint
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/comments/'

        api_client.force_authenticate(user=None)  # Test unauthenticated access
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'comments'
        assert response.data['count'] == 1
        assert response.data['src'][0]['comment'] == 'Test comment via FQID'
        assert response.data['id'] == f"{entry_fqid}/comments"

    def test_get_likes_by_entry_fqid(self, api_client, author_a, author_b):
        """Test GET /api/entries/{ENTRY_FQID}/likes"""
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Create a like via inbox
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        like_data = {
            'type': 'like',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'object': entry.get_api_url()
        }
        api_client.post(inbox_url, like_data, format='json')

        # Test FQID-based likes endpoint
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/likes/'

        api_client.force_authenticate(user=None)  # Test unauthenticated access
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'likes'
        assert response.data['count'] == 1
        assert (
            response.data['src'][0]['author']['id']
            .endswith(f"/api/authors/{author_b.serial}/")
        )
        assert response.data['id'] == f"{entry_fqid}/likes"

    def test_get_comments_by_fqid_friends_only_visible_to_friends(
            self, api_client, author_a, author_b):
        """Test that comments on friends-only entries
        are only visible to friends"""
        # Create friendship
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Friend comments on friends-only entry
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'comment': 'Friends only comment',
            'entry': entry.get_api_url()
        }
        api_client.post(inbox_url, comment_data, format='json')

        # Test FQID-based comments endpoint as friend
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/comments/'

        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1

        # Test as non-friend should be forbidden
        author_c = AuthorFactory()
        api_client.force_authenticate(user=author_c)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_likes_by_fqid_friends_only_visible_to_friends(
            self, api_client, author_a, author_b):
        """Test that likes on friends-only entries
        are only visible to friends"""
        # Create friendship
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Friend likes friends-only entry
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        like_data = {
            'type': 'like',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'object': entry.get_api_url()
        }
        api_client.post(inbox_url, like_data, format='json')

        # Test FQID-based likes endpoint as friend
        entry_fqid = entry.get_api_url()
        encoded_fqid = urllib.parse.quote(entry_fqid, safe='')
        url = f'/api/entries/{encoded_fqid}/likes/'

        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1

        # Test as non-friend should be forbidden
        author_c = AuthorFactory()
        api_client.force_authenticate(user=author_c)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestLikesOnEntryAPI:
    """
    US 7.3: As an author, when someone sends me a public entry
    I want to see the likes.
    """

    def test_story_view_likes_on_public_entry(
            self, api_client, author_a, author_b, author_c):
        """
        Tests that any user (authenticated or not) can view the likes on a
        public entry.
        """
        # Author A creates a public entry
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Author B likes the entry directly via the /likes/ endpoint
        api_client.force_authenticate(user=author_b)
        likes_url = (
            f'/api/authors/{author_a.serial}/entries/{entry.serial}/likes/'
        )
        post_response = api_client.post(likes_url, {}, format='json')
        assert post_response.status_code == status.HTTP_201_CREATED
        assert post_response.data['author']['id'].endswith(
            f"/api/authors/{author_b.serial}/")

        # --- Verification ---
        # 1. Author A (entry owner) can see the like
        api_client.force_authenticate(user=author_a)
        response_a = api_client.get(likes_url)
        assert response_a.status_code == status.HTTP_200_OK
        assert response_a.data['count'] == 1
        assert (response_a.data['src'][0]['author']['id']
                .endswith(f"/api/authors/{author_b.serial}/"))

        # 2. Author C (another user) can see the like
        api_client.force_authenticate(user=author_c)
        response_c = api_client.get(likes_url)
        assert response_c.status_code == status.HTTP_200_OK
        assert response_c.data['count'] == 1

        # 3. Unauthenticated user can see the like
        api_client.force_authenticate(user=None)
        response_unauthenticated = api_client.get(likes_url)
        assert response_unauthenticated.status_code == status.HTTP_200_OK
        assert response_unauthenticated.data['count'] == 1
        assert (response_unauthenticated.data['src'][0]['author']['id']
                .endswith(f"/api/authors/{author_b.serial}/"))

    def test_create_like_on_entry_directly(
            self, api_client, author_a, author_b):
        """
        Tests that an authenticated user can like an entry via
        POST /.../entries/{E}/likes/
        This covers an untested endpoint.
        """
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        api_client.force_authenticate(user=author_b)
        url = f'/api/authors/{author_a.serial}/entries/{entry.serial}/likes/'
        response = api_client.post(url, {}, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['type'] == 'like'
        assert response.data['author']['id'].endswith(
            f"/api/authors/{author_b.serial}/")
        from entries.models import Like
        assert Like.objects.filter(
            author=author_b, object_id=entry.url).exists()


class TestImageEndpoints:
    jpeg_test_image = (
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAP/////////////"
        "////////////////////////////////////////////////////////////"
        "/////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/"
        "aAAgBAQABPxA=")

    png_test_image = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
                      "AAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")

    def test_get_image_by_fqid(self, api_client, author_a):
        # JPEG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/jpeg;base64',
            content=TestImageEndpoints.jpeg_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/jpeg'

        image_entry = EntryFactory(
            author=author_a,
            content_type='application/base64',
            content=TestImageEndpoints.jpeg_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/jpeg'

        # PNG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/png;base64',
            content=TestImageEndpoints.png_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/png'

        image_entry = EntryFactory(
            author=author_a,
            content_type='application/base64',
            content=TestImageEndpoints.png_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/png'

        # 404 - Random FQID
        plain_text_entry = EntryFactory(author=author_a)
        response = api_client.get(
            "/api/entries/j092382/image"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # 404 - Plain text entry
        plain_text_entry = EntryFactory(author=author_a)
        response = api_client.get(
            f"/api/entries/{plain_text_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # 404 - Markdown entry
        markdown_entry = EntryFactory(
            author=author_a,
            content_type='text/markdown')
        response = api_client.get(
            f"/api/entries/{markdown_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_image_by_serials(self, api_client, author_a):
        # JPEG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/jpeg;base64',
            content=TestImageEndpoints.jpeg_test_image)

        response = api_client.get(f"/api/authors/{author_a.serial}"
                                  f"/entries/{image_entry.serial}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/jpeg'

        image_entry = EntryFactory(
            author=author_a,
            content_type='application/base64',
            content=TestImageEndpoints.jpeg_test_image)

        response = api_client.get(
            f"/api/authors/{author_a.serial}"
            f"/entries/{image_entry.serial}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/jpeg'

        # PNG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/png;base64',
            content=TestImageEndpoints.png_test_image)

        response = api_client.get(
            f"/api/authors/{author_a.serial}"
            f"/entries/{image_entry.serial}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/png'

        image_entry = EntryFactory(
            author=author_a,
            content_type='application/base64',
            content=TestImageEndpoints.png_test_image)

        response = api_client.get(
            f"/api/authors/{author_a.serial}"
            f"/entries/{image_entry.serial}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/png'

        # 404 - Random author serial
        response = api_client.get(
            f"/api/authors/{author_a.serial}"
            f"/entries/{str(uuid.uuid4())}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # 404 - Random entry serial
        response = api_client.get(
            f"/api/authors/{str(uuid.uuid4())}"
            f"/entries/{image_entry.serial}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # 404 - Plain text entry
        plain_text_entry = EntryFactory(author=author_a)
        response = api_client.get(
            f"/api/authors/{author_a.serial}"
            f"/entries/{plain_text_entry.serial}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # 404 - Markdown entry
        markdown_entry = EntryFactory(
            author=author_a,
            content_type='text/markdown')
        response = api_client.get(
            f"/api/authors/{author_a.serial}"
            f"/entries/{markdown_entry.serial}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_image_entry_by_fqid_jpeg(self, api_client, author_a):
        # JPEG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/jpeg;base64',
            content=TestImageEndpoints.jpeg_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/jpeg'

    def test_get_image_entry_by_fqid_png(self, api_client, author_a):
        # PNG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/png;base64',
            content=TestImageEndpoints.png_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/png'

    def test_get_image_entry_by_fqid_base64_jpeg(self, api_client, author_a):
        # JPEG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/jpeg;base64',
            content=TestImageEndpoints.jpeg_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/jpeg'

    def test_get_image_entry_by_fqid_base64_png(self, api_client, author_a):
        # PNG image entry
        image_entry = EntryFactory(
            author=author_a,
            content_type='image/png;base64',
            content=TestImageEndpoints.png_test_image)

        response = api_client.get(
            f"/api/entries/{image_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['Content-Type'] == 'image/png'

    def test_get_image_entry_by_fqid_for_markdown_entry(
            self, api_client, author_a):
        # Markdown entry
        markdown_entry = EntryFactory(
            author=author_a,
            content_type='text/markdown')
        response = api_client.get(
            f"/api/entries/{markdown_entry.get_api_url()}/image")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_user_can_access_unlisted_entry_via_direct_link(
            self, api_client, author_a):
        """
        Test that unauthenticated users can access unlisted entries
        via direct link
        """
        # Create an unlisted entry
        unlisted_entry = EntryFactory(
            author=author_a,
            visibility='UNLISTED',
            title='Unlisted Entry',
            content='This is an unlisted entry'
        )

        # Test unauthenticated access via API endpoint
        api_client.force_authenticate(user=None)
        api_url = f'/api/authors/{author_a.serial}/entries/'
        api_url += f'{unlisted_entry.serial}/'
        response = api_client.get(api_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['title'] == 'Unlisted Entry'
        assert response.data['visibility'] == 'UNLISTED'

    def test_unauthenticated_user_cannot_access_friends_only_entry(
            self, api_client, author_a):
        """
        Test that unauthenticated users cannot access friends-only entries,
        even via direct link.
        """
        # Create a friends-only entry
        friends_entry = EntryFactory(
            author=author_a,
            visibility='FRIENDS',
            title='Friends Only Entry',
            content='This is a friends-only entry'
        )

        # Test unauthenticated access via API endpoint
        api_client.force_authenticate(user=None)
        api_url = f'/api/authors/{author_a.serial}/entries/'
        api_url += f'{friends_entry.serial}/'
        response = api_client.get(api_url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
