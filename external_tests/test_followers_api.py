import pytest
import requests
from rest_framework import status
from authors.models import Follow, Author
import urllib.parse

# Pytest mark for all tests in this file
pytestmark = pytest.mark.django_db


class TestFollowersListAPI:
    """
    Tests for the /api/authors/{AUTHOR_SERIAL}/followers/ endpoint.
    """

    def test_get_followers_list_with_data(self, live_server, created_authors):
        """
        Tests GET /api/authors/{serial}/followers/ with accepted followers.
        """
        author_to_follow = created_authors[0]
        follower1 = created_authors[1]
        follower2 = created_authors[2]
        pending_follower = created_authors[3]

        # Create accepted follow relationships
        Follow.objects.create(
            follower=follower1,
            following=author_to_follow,
            status=Follow.Status.ACCEPTED
        )
        Follow.objects.create(
            follower=follower2,
            following=author_to_follow,
            status=Follow.Status.ACCEPTED
        )

        # Create a pending follow (should not appear in followers list)
        Follow.objects.create(
            follower=pending_follower,
            following=author_to_follow,
            status=Follow.Status.PENDING
        )

        url = (
            f'{live_server.url}/api/authors/'
            f'{author_to_follow.serial}/followers/'
        )
        response = requests.get(url)

        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json['type'] == 'followers'
        assert len(response_json['followers']) == 2

        # Check that followers are properly serialized
        follower_ids = {f['id'] for f in response_json['followers']}

        follower1_api_url = f'{
            live_server.url}/api/authors/{
            follower1.serial}/'
        follower2_api_url = f'{
            live_server.url}/api/authors/{
            follower2.serial}/'

        assert follower1_api_url in follower_ids
        assert follower2_api_url in follower_ids

        # Ensure pending follower is not in the list
        pending_follower_api_url = f'{
            live_server.url}/api/authors/{
            pending_follower.serial}'
        assert pending_follower_api_url not in follower_ids


# A factory for creating the foreign author ID in different formats
@pytest.mark.parametrize('follower_type', [
    'local_uuid',   # A local follower identified by their UUID
    'local_fqid',   # A local follower identified by their FQID
    'remote_fqid'   # A remote follower (proxy object) by their FQID
])
class TestFollowerDetailGetAPI:
    """
    Tests for GET /api/authors/{AUTHOR_SERIAL}/followers/{FOREIGN_AUTHOR_ID}
    These tests are parameterized to check for a follower using both their
    local UUID and their URL-encoded FQID.
    """

    def _setup_follower(self, follower_type, live_server,
                        created_authors, remote_server):
        """Helper to create the correct follower and ID for each test case."""
        if follower_type == 'remote_fqid':
            remote_host, _ = remote_server
            # Create a proxy author object for the remote follower
            follower = Author.objects.create(
                username='remote_follower', host=remote_host)
            fqid = f'{remote_host}/authors/{follower.serial}/'
            # Set the URL field for the proxy object
            follower.url = fqid
            follower.save()
            foreign_author_id = urllib.parse.quote(fqid, safe='')
        else:  # Local follower
            follower = created_authors[1]
            if follower_type == 'local_uuid':
                foreign_author_id = follower.serial
            else:  # local_fqid
                fqid = f'{live_server.url}/authors/{follower.serial}/'
                foreign_author_id = urllib.parse.quote(fqid, safe='')
        return follower, foreign_author_id

    def test_check_is_follower_success(self, live_server, created_authors,
                                       remote_server, follower_type):
        """
        Tests that a 200 OK is returned when the foreign author is an
        accepted follower.
        """
        author_to_check = created_authors[0]
        follower, foreign_author_id = self._setup_follower(
            follower_type, live_server, created_authors, remote_server
        )

        # Create an accepted follow relationship
        Follow.objects.create(
            follower=follower,
            following=author_to_check,
            status=Follow.Status.ACCEPTED
        )

        url = (f'{live_server.url}/api/authors/'
               f'{author_to_check.serial}/followers/{foreign_author_id}/')
        response = requests.get(url)

        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert response_json['type'] == 'author'

        # For remote authors, the ID should be their original remote URL
        # For local authors, it should be the local API URL
        if follower_type == 'remote_fqid':
            expected_api_url = follower.url  # Remote author's original URL
        else:
            expected_api_url = (
                f'{live_server.url}/api/authors/{follower.serial}/'
            )
        assert response_json['id'] == expected_api_url
        # The host should reflect the author's actual origin
        assert response_json['host'] == follower.host

    def test_check_is_not_follower(self, live_server, created_authors,
                                   remote_server, follower_type):
        """
        Tests that a 404 Not Found is returned when the foreign author is not
        a follower (i.e. no Follow relationship exists).
        """
        author_to_check = created_authors[0]
        # The "not a follower" can be local or remote, just like a follower
        not_a_follower, foreign_author_id = self._setup_follower(
            follower_type, live_server, created_authors, remote_server
        )

        url = (
            f'{live_server.url}/api/authors/'
            f'{author_to_check.serial}/followers/{foreign_author_id}/'
        )
        response = requests.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_check_is_follower_pending(self, live_server, created_authors,
                                       remote_server, follower_type):
        """
        Tests that a 404 Not Found is returned when the follow request is
        still pending.
        """
        author_to_check = created_authors[0]
        pending_follower, foreign_author_id = self._setup_follower(
            follower_type, live_server, created_authors, remote_server
        )

        # Create a pending follow relationship
        Follow.objects.create(
            follower=pending_follower,
            following=author_to_check,
            status=Follow.Status.PENDING
        )

        url = (
            f'{live_server.url}/api/authors/'
            f'{author_to_check.serial}/followers/{foreign_author_id}/'
        )
        response = requests.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.parametrize('follower_type', [
    'local_fqid',   # A local follower identified by their FQID
    'remote_fqid'   # A remote follower (proxy object) by their FQID
])
class TestFollowerDetailPutAPI:
    """
    Tests for PUT /api/authors/{AUTHOR_SERIAL}/followers/{FOREIGN_AUTHOR_FQID}
    This endpoint is used to approve a follow request. It's parameterized
    to handle approvals for both local and remote followers.
    """

    def _setup_put_follower(
            self, follower_type, live_server,
            created_authors, remote_server):
        """Helper to create the correct follower and ID for each test case."""
        if follower_type == 'remote_fqid':
            remote_host, _ = remote_server
            # Use a unique username to avoid collisions between tests
            follower = Author.objects.create(
                username=f'remote_put_follower_{
                    "".join(
                        filter(str.isalnum, str(remote_server[1])))
                }',
                host=remote_host
            )
            fqid = f'{remote_host}/authors/{follower.serial}/'
            # Set the URL field for the proxy object
            follower.url = fqid
            follower.save()
        else:  # local_fqid
            follower = created_authors[1]
            fqid = f'{live_server.url}/authors/{follower.serial}/'

        encoded_fqid = urllib.parse.quote(fqid, safe='')
        return follower, encoded_fqid

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_approve_follow_request_success(
        self, live_server, created_authors, authenticated_session, auth_method,
        follower_type, remote_server
    ):
        """
        Tests that an authenticated user can approve a pending follow request
        from both local and remote authors.
        """
        author_being_followed = created_authors[0]
        follower, encoded_fqid = self._setup_put_follower(
            follower_type, live_server, created_authors, remote_server
        )

        # Create a pending follow request
        follow = Follow.objects.create(
            follower=follower,
            following=author_being_followed,
            status=Follow.Status.PENDING
        )

        url = (
            f'{live_server.url}/api/authors/'
            f'{author_being_followed.serial}/followers/{encoded_fqid}/'
        )

        if auth_method == 'basic':
            response = requests.put(
                url, auth=(author_being_followed.username, 'password123'))
        else:  # cookie
            session = authenticated_session(author_being_followed)
            response = session.put(url)

        assert response.status_code == status.HTTP_200_OK

        # Verify the follow status is now 'ACCEPTED'
        follow.refresh_from_db()
        assert follow.status == Follow.Status.ACCEPTED

    def test_approve_follow_request_unauthenticated(
        self, live_server, created_authors, follower_type, remote_server
    ):
        """
        Tests that an unauthenticated request to approve a follow fails for
        both local and remote followers.
        """
        author_being_followed = created_authors[0]
        follower, encoded_fqid = self._setup_put_follower(
            follower_type, live_server, created_authors, remote_server
        )

        Follow.objects.create(
            follower=follower,
            following=author_being_followed,
            status=Follow.Status.PENDING
        )

        url = (
            f'{live_server.url}/api/authors/'
            f'{author_being_followed.serial}/followers/{encoded_fqid}/'
        )

        response = requests.put(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_approve_follow_request_wrong_user(
        self, live_server, created_authors, authenticated_session, auth_method,
        follower_type, remote_server
    ):
        """
        Tests that a user cannot approve a follow request intended for another
        user, regardless of whether the follower is local or remote.
        """
        author_being_followed = created_authors[0]
        wrong_user = created_authors[2]  # Authenticates as this user
        follower, encoded_fqid = self._setup_put_follower(
            follower_type, live_server, created_authors, remote_server
        )

        Follow.objects.create(
            follower=follower,
            following=author_being_followed,
            status=Follow.Status.PENDING
        )

        url = (
            f'{live_server.url}/api/authors/'
            f'{author_being_followed.serial}/followers/{encoded_fqid}/'
        )

        if auth_method == 'basic':
            response = requests.put(
                url, auth=(wrong_user.username, 'password123'))
        else:  # cookie
            session = authenticated_session(wrong_user)
            response = session.put(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_approve_nonexistent_request(
        self, live_server, created_authors, authenticated_session,
        follower_type, remote_server
    ):
        """
        Tests that trying to approve a non-existent follow request results
        in a 404 Not Found.
        """
        author_being_followed = created_authors[0]
        # Set up a potential follower, but don't create a Follow object
        _, encoded_fqid = self._setup_put_follower(
            follower_type, live_server, created_authors, remote_server
        )

        session = authenticated_session(author_being_followed)
        url = (
            f'{live_server.url}/api/authors/'
            f'{author_being_followed.serial}/followers/{encoded_fqid}/'
        )

        response = session.put(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestFollowerDetailDeleteAPI:
    """
    Tests for DELETE /api/authors/{AUTHOR_SERIAL}/followers/
    {FOREIGN_AUTHOR_FQID}
    This endpoint is used by a follower to unfollow an author.
    """

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_unfollow_success(
        self, live_server, created_authors, authenticated_session, auth_method
    ):
        """
        Tests that a follower can successfully unfollow another author.
        """
        followed_author = created_authors[0]
        follower = created_authors[1]

        # Create an accepted follow relationship
        follow = Follow.objects.create(
            follower=follower,
            following=followed_author,
            status=Follow.Status.ACCEPTED
        )

        follower_fqid = f'{live_server.url}/authors/{follower.serial}'
        encoded_fqid = urllib.parse.quote(follower_fqid, safe='')
        url = (
            f'{live_server.url}/api/authors/'
            f'{followed_author.serial}/followers/{encoded_fqid}/'
        )

        # Authenticate as the follower to perform the unfollow action
        if auth_method == 'basic':
            response = requests.delete(
                url, auth=(follower.username, 'password123'))
        else:  # cookie
            session = authenticated_session(follower)
            response = session.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Follow.objects.filter(pk=follow.pk).exists()

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_author_cannot_remove_follower(
        self, live_server, created_authors, authenticated_session, auth_method
    ):
        """
        Tests that an author cannot remove one of their own followers.
        This action should be forbidden.
        """
        followed_author = created_authors[0]
        follower = created_authors[1]

        Follow.objects.create(
            follower=follower,
            following=followed_author,
            status=Follow.Status.ACCEPTED
        )

        follower_fqid = f'{live_server.url}/authors/{follower.serial}'
        encoded_fqid = urllib.parse.quote(follower_fqid, safe='')
        url = (
            f'{live_server.url}/api/authors/'
            f'{followed_author.serial}/followers/{encoded_fqid}/'
        )

        # Authenticate as the author being followed, who should not be
        # able to remove their follower.
        if auth_method == 'basic':
            response = requests.delete(
                url, auth=(followed_author.username, 'password123'))
        else:  # cookie
            session = authenticated_session(followed_author)
            response = session.delete(url)

        # An author cannot remove their followers.
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_delete_unfollow_wrong_user(
        self, live_server, created_authors, authenticated_session, auth_method
    ):
        """
        Tests that a user who is not part of the follow relationship cannot
        delete it.
        """
        followed_author = created_authors[0]
        follower = created_authors[1]
        wrong_user = created_authors[2]

        Follow.objects.create(
            follower=follower,
            following=followed_author,
            status=Follow.Status.ACCEPTED
        )

        follower_fqid = f'{live_server.url}/authors/{follower.serial}'
        encoded_fqid = urllib.parse.quote(follower_fqid, safe='')
        url = (
            f'{live_server.url}/api/authors/'
            f'{followed_author.serial}/followers/{encoded_fqid}/'
        )

        if auth_method == 'basic':
            response = requests.delete(
                url, auth=(wrong_user.username, 'password123'))
        else:  # cookie
            session = authenticated_session(wrong_user)
            response = session.delete(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_unfollow_unauthenticated(
        self, live_server, created_authors
    ):
        """
        Tests that an unauthenticated request to unfollow fails.
        """
        followed_author = created_authors[0]
        follower = created_authors[1]

        Follow.objects.create(
            follower=follower,
            following=followed_author,
            status=Follow.Status.ACCEPTED
        )

        follower_fqid = f'{live_server.url}/authors/{follower.serial}'
        encoded_fqid = urllib.parse.quote(follower_fqid, safe='')
        url = (
            f'{live_server.url}/api/authors/'
            f'{followed_author.serial}/followers/{encoded_fqid}/'
        )

        response = requests.delete(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.parametrize("auth_method", ['basic', 'cookie'])
    def test_delete_nonexistent_relationship(
        self, live_server, created_authors, authenticated_session, auth_method
    ):
        """
        Tests that deleting a non-existent follow relationship returns 404.
        """
        author1 = created_authors[0]
        author2 = created_authors[1]

        # No follow relationship exists
        author2_fqid = f'{live_server.url}/authors/{author2.serial}'
        encoded_fqid = urllib.parse.quote(author2_fqid, safe='')
        url = (
            f'{live_server.url}/api/authors/'
            f'{author1.serial}/followers/{encoded_fqid}/'
        )

        if auth_method == 'basic':
            response = requests.delete(
                url, auth=(author2.username, 'password123'))
        else:  # cookie
            session = authenticated_session(author2)
            response = session.delete(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
