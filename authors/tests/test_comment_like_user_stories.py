import pytest
from rest_framework.test import APIClient
from rest_framework import status
from .factories import AuthorFactory, FollowFactory
from entries.tests.factories import EntryFactory
from entries.models import Comment, Like
from django.contrib.contenttypes.models import ContentType

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
    """Create a third test author who is not friends with anyone"""
    return AuthorFactory()


class TestCommentingStory:
    """US 7.0: As an author, I want to comment on entries that I can access."""

    def test_story_can_comment_on_public_entry(
            self, api_client, author_a, author_b):
        # Author A creates a public entry
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Author B (any authenticated user) comments on it
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'comment': 'A witty reply to a public entry.',
            'contentType': 'text/plain',
            'entry': entry.get_api_url()}
        response = api_client.post(inbox_url, comment_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert Comment.objects.filter(author=author_b, entry=entry).exists()

    def test_story_can_comment_on_friends_entry_as_friend(
            self, api_client, author_a, author_b):
        # Author A and B are friends
        FollowFactory.create_friendship(author1=author_a, author2=author_b)
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Author B (a friend) comments on it
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'comment': 'A comment between friends.',
            'entry': entry.get_api_url()}
        response = api_client.post(inbox_url, comment_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert Comment.objects.filter(author=author_b, entry=entry).exists()

    def test_story_cannot_comment_on_friends_entry_as_non_friend(
            self, api_client, author_a, author_c):
        # Author A and C are not friends
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Author C (not a friend) attempts to comment
        api_client.force_authenticate(user=author_c)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'author': {
                'id': author_c.get_api_url(),
                'displayName': author_c.display_name,
                'host': author_c.host
            },
            'comment': 'I should not be able to post this.',
            'entry': entry.get_api_url()}
        response = api_client.post(inbox_url, comment_data, format='json')

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Comment.objects.filter(
            author=author_c, entry=entry).exists()


class TestLikingEntryStory:
    """US 7.1: As an author, I want to like entries that I can access."""

    def test_story_can_like_public_entry(
            self, api_client, author_a, author_b):
        # Author A creates a public entry
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Author B likes the entry
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

        response = api_client.post(inbox_url, like_data, format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert Like.objects.filter(
            author=author_b, object_id=entry.url).exists()

    def test_story_cannot_like_friends_entry_as_non_friend(
            self, api_client, author_a, author_c):
        # Author A makes a friends-only entry
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Author C (not a friend) tries to like the entry
        api_client.force_authenticate(user=author_c)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        like_data = {
            'type': 'like',
            'author': {
                'id': author_c.get_api_url(),
                'displayName': author_c.display_name,
                'host': author_c.host
            },
            'object': entry.get_api_url()
        }

        response = api_client.post(inbox_url, like_data, format='json')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_story_cannot_like_entry_twice(
            self, api_client, author_a, author_b):
        # Author A creates a public entry
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Author B likes the entry
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

        response = api_client.post(inbox_url, like_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Author B tries to like the same entry again
        response = api_client.post(inbox_url, like_data, format='json')
        assert response.status_code == status.HTTP_409_CONFLICT

        # Only one like should exist
        assert Like.objects.filter(
            author=author_b, object_id=entry.url).count() == 1


class TestLikingCommentStory:
    """US 7.2: As an author, I want to like comments that I can access."""

    def test_story_can_like_comment_on_public_entry(
            self, api_client, author_a, author_b, author_c):
        # Author A makes a public entry
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Author B comments on the entry
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'comment': 'Great entry!',
            'entry': entry.get_api_url()
        }
        response = api_client.post(inbox_url, comment_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Get the comment ID from the response
        comment_id = response.data['id']
        comment = Comment.objects.get(author=author_b, entry=entry)

        # Author C likes the comment
        api_client.force_authenticate(user=author_c)
        # Like should be sent to entry author's inbox (author_a)
        entry_author_inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        like_data = {
            'type': 'like',
            'author': {
                'id': author_c.get_api_url(),
                'displayName': author_c.display_name,
                'host': author_c.host
            },
            'object': comment_id
        }
        response = api_client.post(
            entry_author_inbox_url,
            like_data,
            format='json')

        assert response.status_code == status.HTTP_201_CREATED
        assert Like.objects.filter(
            author=author_c, object_id=comment.url).exists()

    def test_story_cannot_like_comment_on_friends_entry_as_non_friend(
            self, api_client, author_a, author_b, author_c):
        # Author A and B are friends
        FollowFactory.create_friendship(author1=author_a, author2=author_b)

        # Author A makes a friends-only entry
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        # Author B comments on the entry
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'comment': 'Great entry!',
            'entry': entry.get_api_url()
        }
        response = api_client.post(inbox_url, comment_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Get the comment ID from the response
        comment_id = response.data['id']
        Comment.objects.get(author=author_b, entry=entry)

        # Author C (not a friend) tries to like the comment
        api_client.force_authenticate(user=author_c)
        # Like should be sent to entry author's inbox (author_a)
        entry_author_inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        like_data = {
            'type': 'like',
            'author': {
                'id': author_c.get_api_url(),
                'displayName': author_c.display_name,
                'host': author_c.host
            },
            'object': comment_id
        }
        response = api_client.post(
            entry_author_inbox_url,
            like_data,
            format='json')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_story_cannot_like_comment_twice(
            self, api_client, author_a, author_b, author_c):
        # Author A makes a public entry
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        # Author B comments on the entry
        api_client.force_authenticate(user=author_b)
        inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        comment_data = {
            'type': 'comment',
            'author': {
                'id': author_b.get_api_url(),
                'displayName': author_b.display_name,
                'host': author_b.host
            },
            'comment': 'Great entry!',
            'entry': entry.get_api_url()
        }
        response = api_client.post(inbox_url, comment_data, format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Get the comment ID from the response
        comment_id = response.data['id']
        comment = Comment.objects.get(author=author_b, entry=entry)

        # Author C likes the comment
        api_client.force_authenticate(user=author_c)
        # Like should be sent to entry author's inbox (author_a)
        entry_author_inbox_url = f'/api/authors/{author_a.serial}/inbox/'
        like_data = {
            'type': 'like',
            'author': {
                'id': author_c.get_api_url(),
                'displayName': author_c.display_name,
                'host': author_c.host
            },
            'object': comment_id
        }
        response = api_client.post(
            entry_author_inbox_url,
            like_data,
            format='json')
        assert response.status_code == status.HTTP_201_CREATED

        # Author C tries to like the same comment again
        response = api_client.post(
            entry_author_inbox_url,
            like_data,
            format='json')
        assert response.status_code == status.HTTP_409_CONFLICT

        # Only one like should exist
        assert Like.objects.filter(
            author=author_c,
            content_type=ContentType.objects.get_for_model(Comment),
            object_id=comment.url).count() == 1


class TestLikeFanOutMultiNode:
    """Test that likes are properly distributed to all users who can
    see the entry across nodes."""

    def test_like_public_entry_fans_out_to_all_followers(self, api_client):
        """
        When someone likes a public entry, the like should be sent to
        all followers of the entry author who are on remote nodes.
        """
        from unittest.mock import patch
        from .factories import AuthorFactory
        from authors.models import RemoteNode, Follow
        from entries.tests.factories import EntryFactory
        from entries.models import Like

        # Create entry author on Node A
        entry_author = AuthorFactory(host="http://node-a.com/")

        # Create entry liker on Node B
        liker = AuthorFactory(host="http://node-b.com/")

        # Create followers on different nodes
        follower_node_b = AuthorFactory(host="http://node-b.com/")
        follower_node_c = AuthorFactory(host="http://node-c.com/")

        # Set up follow relationships
        Follow.objects.create(
            follower=follower_node_b,
            following=entry_author,
            status=Follow.Status.ACCEPTED
        )
        Follow.objects.create(
            follower=follower_node_c,
            following=entry_author,
            status=Follow.Status.ACCEPTED
        )

        # Create remote nodes
        RemoteNode.objects.create(
            host="http://node-b.com/",
            outgoing_username="test_user_b",
            outgoing_password="test_pass_b",
            is_active=True
        )
        RemoteNode.objects.create(
            host="http://node-c.com/",
            outgoing_username="test_user_c",
            outgoing_password="test_pass_c",
            is_active=True
        )

        # Create a public entry
        entry = EntryFactory(author=entry_author, visibility='PUBLIC')

        # Mock the requests.post to track outgoing like notifications
        with patch('authors.views.requests.post') as mock_post:
            mock_post.return_value.raise_for_status = lambda: None

            # Simulate liker creating a like (this should trigger fan-out)
            Like.objects.create(
                author=liker,
                content_object=entry,
                object_id=entry.url,
                url=f"{liker.host}authors/{liker.serial}/liked/test-like-123/"
            )

            # Verify that likes were sent to both remote followers
            assert mock_post.call_count == 2

            # Check that both followers received the like
            # First positional arg is the URL
            call_urls = [call[0][0] for call in mock_post.call_args_list]
            expected_urls = [
                f"{follower_node_b.get_api_url()}inbox/",
                f"{follower_node_c.get_api_url()}inbox/"
            ]

            for expected_url in expected_urls:
                assert expected_url in call_urls, \
                    f"Like not sent to {expected_url}"

            # Verify the like payload structure
            like_payload = mock_post.call_args_list[0][1]['json']
            assert like_payload['type'] == 'like'
            assert like_payload['object'] == entry.url
            assert like_payload['author']['id'] == liker.get_api_url()

    def test_like_friends_entry_fans_out_to_friends_only(self, api_client):
        """
        When someone likes a friends-only entry, the like should only
        be sent to friends of the entry author who are on remote nodes.
        """
        from unittest.mock import patch
        from .factories import AuthorFactory
        from authors.models import RemoteNode, Follow
        from entries.tests.factories import EntryFactory
        from entries.models import Like

        # Create entry author on Node A
        entry_author = AuthorFactory(host="http://node-a.com/")

        # Create entry liker on Node B
        liker = AuthorFactory(host="http://node-b.com/")

        # Create a friend and a regular follower on different nodes
        friend_node_b = AuthorFactory(host="http://node-b.com/")
        follower_node_c = AuthorFactory(host="http://node-c.com/")

        # Set up relationships
        # Friend relationship (mutual follows)
        Follow.objects.create(
            follower=friend_node_b,
            following=entry_author,
            status=Follow.Status.ACCEPTED
        )
        Follow.objects.create(
            follower=entry_author,
            following=friend_node_b,
            status=Follow.Status.ACCEPTED
        )

        # Regular follower (not mutual)
        Follow.objects.create(
            follower=follower_node_c,
            following=entry_author,
            status=Follow.Status.ACCEPTED
        )

        # Create remote nodes
        RemoteNode.objects.create(
            host="http://node-b.com/",
            outgoing_username="test_user_b",
            outgoing_password="test_pass_b",
            is_active=True
        )
        RemoteNode.objects.create(
            host="http://node-c.com/",
            outgoing_username="test_user_c",
            outgoing_password="test_pass_c",
            is_active=True
        )

        # Create a friends-only entry
        entry = EntryFactory(author=entry_author, visibility='FRIENDS')

        # Mock the requests.post to track outgoing like notifications
        with patch('authors.views.requests.post') as mock_post:
            mock_post.return_value.raise_for_status = lambda: None

            # Simulate liker creating a like (this should trigger fan-out)
            Like.objects.create(
                author=liker,
                content_object=entry,
                object_id=entry.url,
                url=f"{liker.host}authors/{liker.serial}/liked/test-like-456/"
            )

            # Verify that like was sent only to the friend, not the regular
            # follower
            assert mock_post.call_count == 1

            # Check that only the friend received the like
            # First positional arg is the URL
            call_url = mock_post.call_args_list[0][0][0]
            expected_url = f"{friend_node_b.get_api_url()}inbox/"
            assert call_url == expected_url

            # Verify the like payload
            like_payload = mock_post.call_args_list[0][1]['json']
            assert like_payload['type'] == 'like'
            assert like_payload['object'] == entry.url
