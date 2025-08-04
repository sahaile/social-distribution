import pytest
import urllib.parse
from rest_framework.test import APIClient
from rest_framework import status
from .factories import AuthorFactory, FollowFactory
from authors.models import Follow

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


class TestFollowersListAPI:
    """Test GET /api/authors/{serial}/followers/ endpoint"""

    def test_get_followers_list_empty(self, api_client, author_a):
        """Test getting followers list when no followers exist"""
        url = f'/api/authors/{author_a.serial}/followers/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'followers'
        assert response.data['followers'] == []

    def test_get_followers_list_with_data(self, api_client, author_a):
        """Test getting followers list with accepted followers"""
        # Create some followers
        follower1 = AuthorFactory()
        follower2 = AuthorFactory()

        # Create accepted follow relationships
        FollowFactory.create_accepted(follower=follower1, following=author_a)
        FollowFactory.create_accepted(follower=follower2, following=author_a)

        # Create a pending follow (should not appear)
        FollowFactory(
            follower=AuthorFactory(),
            following=author_a,
            status='PENDING')

        url = f'/api/authors/{author_a.serial}/followers/'
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['type'] == 'followers'
        assert len(response.data['followers']) == 2

        # Check that followers are properly serialized
        follower_ids = {f['id'] for f in response.data['followers']}
        assert any(id.endswith(
            f'/api/authors/{follower1.serial}/') for id in follower_ids)
        assert any(id.endswith(
            f'/api/authors/{follower2.serial}/') for id in follower_ids)

    def test_get_followers_by_fqid(self, api_client, author_a):
        """Test getting followers using FQID instead of serial"""
        follower = AuthorFactory()
        FollowFactory.create_accepted(follower=follower, following=author_a)

        # Use URL-encoded FQID
        fqid = author_a.get_api_url()
        encoded_fqid = urllib.parse.quote(fqid, safe='')
        url = f'/api/authors/{encoded_fqid}/followers/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestFollowerDetailAPI:
    """Test GET/PUT/DELETE /api/authors/{serial}/followers/{fqid}/ endpoint"""

    def test_check_if_following_exists(self, api_client, author_a, author_b):
        """Test checking if foreign author is following"""
        # Create accepted follow relationship
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        # Use the foreign author's serial
        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'].endswith(f'/api/authors/{author_b.serial}/')
        assert response.data['type'] == 'author'

    def test_check_if_following_not_exists(
            self, api_client, author_a, author_b):
        """Test checking if foreign author is NOT following"""
        # No follow relationship exists
        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_check_if_following_pending_not_visible(
            self, api_client, author_a, author_b):
        """Test that pending follows don't show as following"""
        # Create pending follow relationship
        FollowFactory(follower=author_b, following=author_a, status='PENDING')

        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_approve_follow_request(self, api_client, author_a, author_b):
        """Test approving a follow request (PUT)"""
        # Create pending follow request
        follow = FollowFactory(
            follower=author_b,
            following=author_a,
            status='PENDING')

        # Authenticate as the author who is being followed
        api_client.force_authenticate(user=author_a)

        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.put(url)

        assert response.status_code == status.HTTP_200_OK
        follow.refresh_from_db()
        assert follow.status == 'ACCEPTED'

    def test_approve_follow_request_unauthorized(
            self, api_client, author_a, author_b, author_c):
        """Test that only the target author can approve follow requests"""
        # Create pending follow request
        FollowFactory(follower=author_b, following=author_a, status='PENDING')

        # Authenticate as a different author
        api_client.force_authenticate(user=author_c)

        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.put(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approve_nonexistent_follow_request(
            self, api_client, author_a, author_b):
        """Test approving a follow request that doesn't exist"""
        api_client.force_authenticate(user=author_a)

        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.put(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_author_cannot_remove_follower(
            self, api_client, author_a, author_b):
        """Test that an author cannot remove their follower (DELETE)"""
        # Create accepted follow relationship where B follows A
        follow = FollowFactory.create_accepted(
            follower=author_b, following=author_a)

        # Authenticate as A (the one being followed)
        api_client.force_authenticate(user=author_a)

        url = f'/api/authors/{author_a.serial}/followers/{author_b.serial}/'

        response = api_client.delete(url)

        # A should NOT be able to remove their follower B.
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert Follow.objects.filter(pk=follow.pk).exists()

    def test_unfollow_author(self, api_client, author_a, author_b):
        """Test unfollowing another author (DELETE)"""
        # Create accepted follow relationship
        follow = FollowFactory.create_accepted(
            follower=author_a, following=author_b)

        # Authenticate as the follower
        api_client.force_authenticate(user=author_a)

        url = f'/api/authors/{author_b.serial}/followers/{author_a.serial}/'

        response = api_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Follow.objects.filter(pk=follow.pk).exists()

    def test_unfollow_author_unauthorized(
            self, api_client, author_a, author_b, author_c):
        """Test that only a user in the relationship can unfollow"""
        # Create accepted follow relationship
        FollowFactory.create_accepted(
            follower=author_a, following=author_b)

        # Authenticate as a different author
        api_client.force_authenticate(user=author_c)

        url = f'/api/authors/{author_b.serial}/followers/{author_a.serial}/'

        response = api_client.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestInboxFollowRequests:
    """Test follow request handling in the inbox"""

    def test_send_follow_request_to_inbox(
            self, api_client, author_a, author_b):
        """Test sending a follow request to another author's inbox"""
        api_client.force_authenticate(user=author_b)

        # Get the full, request-aware URL for the object (author_a)
        object_res = api_client.get(f'/api/authors/{author_a.serial}/')
        object_id = object_res.data['id']
        print(f"object_id: {object_id}")
        # Get the full, request-aware URL for the actor (author_b)
        actor_res = api_client.get(f'/api/authors/{author_b.serial}/')
        actor_id = actor_res.data['id']

        url = f'/api/authors/{author_a.serial}/inbox/'
        data = {
            'type': 'follow',
            'summary': f'{
                author_b.display_name} wants to follow {
                author_a.display_name}',
            'actor': {
                'type': 'author',
                'id': actor_id,
                'host': author_b.host,
                'displayName': author_b.display_name,
                'github': author_b.github,
                'profileImage': author_b.profile_image,
                'web': author_b.get_web_url()},
            'object': {
                'type': 'author',
                    'id': object_id,
                    'host': author_a.host,
                    'displayName': author_a.display_name,
                    'github': author_a.github,
                    'profileImage': author_a.profile_image,
                'web': author_a.get_web_url()}}

        response = api_client.post(url, data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['type'] == 'follow'
        assert response.data['actor']['id'].endswith(
            f'/api/authors/{author_b.serial}/')
        assert response.data['object']['id'].endswith(
            f'/api/authors/{author_a.serial}/')

        # Verify follow request was created
        follow = Follow.objects.get(follower=author_b, following=author_a)
        assert follow.status == Follow.Status.PENDING

    def test_send_follow_request_wrong_object(
            self, api_client, author_a, author_b, author_c):
        """Test sending follow request with wrong object (not inbox owner)"""
        api_client.force_authenticate(user=author_b)

        url = f'/api/authors/{author_a.serial}/inbox/'
        data = {
            'type': 'follow',
            'actor': {
                'type': 'author',
                'id': author_b.get_api_url(),
            },
            'object': {
                'type': 'author',
                'id': author_c.get_api_url(),  # Wrong object!
            }
        }

        response = api_client.post(url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_resend_follow_request(self, api_client, author_a, author_b):
        """Test re-sending a previously rejected follow request"""
        # Create a rejected follow
        FollowFactory.create_rejected(follower=author_b, following=author_a)

        api_client.force_authenticate(user=author_b)

        # Get the full, request-aware URL for the object (author_a)
        object_res = api_client.get(f'/api/authors/{author_a.serial}/')
        object_id = object_res.data['id']
        # Get the full, request-aware URL for the actor (author_b)
        actor_res = api_client.get(f'/api/authors/{author_b.serial}/')
        actor_id = actor_res.data['id']

        url = f'/api/authors/{author_a.serial}/inbox/'
        data = {
            'type': 'follow',
            'actor': {
                'type': 'author',
                'id': actor_id,
            },
            'object': {
                'type': 'author',
                'id': object_id,
            }
        }

        response = api_client.post(url, data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        # Verify the follow request is now pending
        follow = Follow.objects.get(follower=author_b, following=author_a)
        assert follow.status == Follow.Status.PENDING
