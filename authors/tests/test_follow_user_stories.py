import pytest
from rest_framework.test import APIClient
from rest_framework import status
from .factories import AuthorFactory, FollowFactory
from entries.tests.factories import EntryFactory

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


class TestFollowUserStories:
    """Tests for user stories related to following,
    friends, and access control."""

    def test_story_view_pending_follow_requests(
            self, api_client, author_a, author_b, author_c):
        """
        Story 6.3: As an author, I want to know if I have
        "follow requests," so I can approve them.
        Tests GET /api/authors/{AUTHOR_SERIAL}/follow-requests/
        """
        # B and C send follow requests to A
        FollowFactory(follower=author_b, following=author_a, status='PENDING')
        FollowFactory(follower=author_c, following=author_a, status='PENDING')
        # An accepted follow that should not appear
        FollowFactory.create_accepted(
            follower=AuthorFactory(), following=author_a)

        # Authenticate as author A
        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/follow-requests/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2
        requester_ids = {item['actor']['id'] for item in response.data}
        # Check that the API URLs of the requesters are present
        assert any(id.endswith(
            f'/api/authors/{author_b.serial}/') for id in requester_ids)
        assert any(id.endswith(
            f'/api/authors/{author_c.serial}/') for id in requester_ids)

    def test_story_view_following_list(
            self, api_client, author_a, author_b, author_c):
        """
        Story 6.7: As an author, my node will know about who I am following.
        Tests GET /api/authors/{AUTHOR_SERIAL}/following/
        """
        # A follows B and C
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_a, following=author_c)
        # A has a pending request to follow someone else (should not appear)
        FollowFactory(
            follower=author_a,
            following=AuthorFactory(),
            status='PENDING')

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/following/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'following'
        assert len(response.data['following']) == 2
        following_ids = {item['id'] for item in response.data['following']}
        assert any(
            id.endswith(f'/api/authors/{author_b.serial}/')
            for id in following_ids
        )
        assert any(
            id.endswith(f'/api/authors/{author_c.serial}/')
            for id in following_ids
        )

    def test_story_unfriend_revokes_access(
            self, api_client, author_a, author_b):
        """
        Story 6.5 & 6.6: Unfriending revokes access to friends-only entries.
        """
        # 1. A and B become friends
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        # 2. B creates a friends-only entry
        friends_entry = EntryFactory(author=author_b, visibility='FRIENDS')

        # 3. A can see B's friends-only entry
        api_client.force_authenticate(user=author_a)
        entry_url = (
            f'/api/authors/{author_b.serial}/entries/{friends_entry.serial}/'
        )
        response = api_client.get(entry_url)
        assert response.status_code == status.HTTP_200_OK

        # 4. A unfollows B, breaking the friendship.
        # The API endpoint is DELETE
        # /api/authors/{FOLLOWED}/followers/{FOLLOWER}/
        # Here, author_a (the follower) is unfollowing author_b (the followed)
        # The user making the request (author_a) must match the follower's
        # FQID.
        unfollow_url = f'/api/authors/{
            author_b.serial}/followers/{
            author_a.serial}/'
        response = api_client.delete(unfollow_url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # 5. A can NO LONGER see B's friends-only entry
        response = api_client.get(entry_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_story_unfollow_revokes_stream_access_to_unlisted(
            self, api_client, author_a, author_b):
        """
        Story 6.0 & 6.4: Unfollowing revokes access
        to unlisted entries in the stream.
        """
        # 1. B creates a public and an unlisted entry
        public_entry = EntryFactory(author=author_b, visibility='PUBLIC')
        unlisted_entry = EntryFactory(author=author_b, visibility='UNLISTED')

        # 2. A follows B
        FollowFactory.create_accepted(follower=author_a, following=author_b)

        # 3. A can see both of B's entries in their stream
        api_client.force_authenticate(user=author_a)
        entries_url = f'/api/authors/{author_b.serial}/entries/'
        response = api_client.get(entries_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 2

        # 4. A unfollows B
        unfollow_url = f'/api/authors/{
            author_b.serial}/followers/{
            author_a.serial}/'
        response = api_client.delete(unfollow_url)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        # 5. A can now only see B's public entry in the stream, not the
        # unlisted one
        response = api_client.get(entries_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert response.data['src'][0]['id'] == public_entry.get_api_url()

        # 6. A can still access the unlisted entry directly via its link, as
        # per spec
        unlisted_url = (
            f'/api/authors/{author_b.serial}/entries/'
            f'{unlisted_entry.serial}/'
        )
        response = api_client.get(unlisted_url)
        assert response.status_code == status.HTTP_200_OK
