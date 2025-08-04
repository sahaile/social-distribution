import pytest
from rest_framework.test import APIClient
from rest_framework import status
from authors.tests.factories import (
    AuthorFactory,
    RemoteAuthorFactory,
    RemoteNodeFactory,
    FollowFactory,
)
from entries.tests.factories import EntryFactory

"""Local Testing"""


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


@pytest.mark.django_db
class TestEntriesVisibility:

    def test_public_entry_visibility(self, api_client, author_a):
        entry = EntryFactory(author=author_a, visibility='PUBLIC')

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'

        api_client.force_authenticate(user=None)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) in entry_ids

    def test_unlisted_entry_visibility(self, api_client, author_a, author_b):
        entry = EntryFactory(author=author_a, visibility='UNLISTED')

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'

        # author's followers should see the unlisted entry
        FollowFactory.create_accepted(follower=author_b, following=author_a)
        api_client.force_authenticate(user=author_b)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) in entry_ids

        # non-follower should not see the unlisted entry
        api_client.force_authenticate(user=None)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) not in entry_ids

    def test_friends_entry_visibility(self, api_client, author_a, author_b):
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'

        # friend (author_b) should see the friends-only entry
        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)
        api_client.force_authenticate(user=author_b)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) in entry_ids

        # non-friend should not see the friends-only entry
        api_client.force_authenticate(user=None)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) not in entry_ids

    def test_friends_stream_entries(self, api_client, author_a, author_b):
        public_entry = EntryFactory(author=author_a, visibility='PUBLIC')
        unlisted_entry = EntryFactory(author=author_a, visibility='UNLISTED')
        friends_entry = EntryFactory(author=author_a, visibility='FRIENDS')

        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        api_client.force_authenticate(user=author_b)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(public_entry.serial) in entry_ids
        assert str(unlisted_entry.serial) in entry_ids
        assert str(friends_entry.serial) in entry_ids

    def test_public_and_unlisted_entries_by_link(self, api_client, author_a):
        public_entry = EntryFactory(author=author_a, visibility='PUBLIC')
        unlisted_entry = EntryFactory(author=author_a, visibility='UNLISTED')

        api_client.force_authenticate(user=None)

        url_public = (
            f'/api/authors/{author_a.serial}/entries/{public_entry.serial}/'
        )
        response = api_client.get(url_public)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == public_entry.get_api_url()

        url_unlisted = (
            f'/api/authors/{author_a.serial}/entries/{unlisted_entry.serial}/'
        )
        response = api_client.get(url_unlisted)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == unlisted_entry.get_api_url()

    def test_friends_entry_access(self, api_client, author_a, author_b):
        entry = EntryFactory(author=author_a, visibility='FRIENDS')

        url = f'/api/authors/{author_a.serial}/entries/{entry.serial}/'
        api_client.force_authenticate(user=author_b)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(follower=author_b, following=author_a)

        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == entry.get_api_url()

    def test_deleted_entry_access(self, api_client, author_a, author_b):
        entry = EntryFactory(
            author=author_a,
            visibility='PUBLIC',
            is_deleted='True')

        url = f'/api/authors/{author_a.serial}/entries/{entry.serial}/'
        api_client.force_authenticate(user=author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        api_client.force_authenticate(user=author_b)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


"""Remote Testing"""


@pytest.fixture
def local_node():
    node = RemoteNodeFactory(
        host="https://local.example.com/",
        is_active=True,
        outgoing_username="local_out_user",
        outgoing_password="local_out_pass",
        incoming_username="remote_out_user",
        incoming_password="remote_out_pass"
    )
    return node


@pytest.fixture
def remote_node():
    node = RemoteNodeFactory(
        host="https://remote.example.com/",
        is_active=True,
        outgoing_username="remote_out_user",
        outgoing_password="remote_out_pass",
        incoming_username="local_out_user",
        incoming_password="local_out_pass"
    )
    return node


@pytest.fixture
def local_author_a(local_node):
    return RemoteAuthorFactory(host=local_node.host)


@pytest.fixture
def local_author_b(local_node):
    return RemoteAuthorFactory(host=local_node.host)


@pytest.fixture
def remote_author_a(remote_node):
    return RemoteAuthorFactory(host=remote_node.host)


@pytest.fixture
def remote_author_b(remote_node):
    return RemoteAuthorFactory(host=remote_node.host)


@pytest.mark.django_db
class TestRemoteEntriesVisibility:
    def remote_test_public_entry_visibility(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        entry = EntryFactory(author=local_author_a, visibility='PUBLIC')

        api_client.force_authenticate(user=local_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'

        api_client.force_authenticate(user=remote_author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) in entry_ids

    def remote_test_unlisted_entry_visibility(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        entry = EntryFactory(author=local_author_a, visibility='UNLISTED')

        api_client.force_authenticate(user=local_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'

        # author's followers should see the unlisted entry
        FollowFactory.create_accepted(
            follower=remote_author_a,
            following=local_author_a)
        api_client.force_authenticate(user=remote_author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) in entry_ids

        # non-follower should not see the unlisted entry
        api_client.force_authenticate(user=None)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) not in entry_ids

    def remote_test_friends_entry_visibility(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        entry = EntryFactory(author=local_author_a, visibility='FRIENDS')

        api_client.force_authenticate(user=local_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'

        # friend (author_b) should see the friends-only entry
        FollowFactory.create_accepted(
            follower=local_author_a,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_a,
            following=local_author_a)
        api_client.force_authenticate(user=remote_author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) in entry_ids

        # non-friend should not see the friends-only entry
        api_client.force_authenticate(user=None)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(entry.serial) not in entry_ids

    def remote_test_friends_stream_entries(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        public_entry = EntryFactory(author=local_author_a, visibility='PUBLIC')
        unlisted_entry = EntryFactory(
            author=local_author_a, visibility='UNLISTED')
        friends_entry = EntryFactory(
            author=local_author_a, visibility='FRIENDS')

        FollowFactory.create_accepted(
            follower=local_author_a,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_a,
            following=local_author_a)

        api_client.force_authenticate(user=remote_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]
        assert str(public_entry.serial) in entry_ids
        assert str(unlisted_entry.serial) in entry_ids
        assert str(friends_entry.serial) in entry_ids

    def remote_test_public_and_unlisted_entries_by_link(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        public_entry = EntryFactory(author=local_author_a, visibility='PUBLIC')
        unlisted_entry = EntryFactory(author=author_a, visibility='UNLISTED')

        api_client.force_authenticate(user=None)

        url_public = f'/api/authors/{local_author_a.serial}/' \
            f'entries/{public_entry.serial}/'

        response = api_client.get(url_public)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == public_entry.get_api_url()

        url_unlisted = f'/api/authors/{local_author_a.serial}/' \
            f'entries/{unlisted_entry.serial}/'

        response = api_client.get(url_unlisted)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == unlisted_entry.get_api_url()

    def remote_test_friends_entry_access(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        entry = EntryFactory(author=local_author_a, visibility='FRIENDS')

        url = f'/api/authors/{local_author_a.serial}/entries/{entry.serial}/'
        api_client.force_authenticate(user=remote_author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        FollowFactory.create_accepted(
            follower=local_author_a,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_a,
            following=local_author_a)

        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == entry.get_api_url()

    def remote_test_deleted_entry_access(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b):
        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        entry = EntryFactory(
            author=local_author_a,
            visibility='PUBLIC',
            is_deleted='True')

        url = f'/api/authors/{local_author_a.serial}/entries/{entry.serial}/'
        api_client.force_authenticate(user=local_author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        api_client.force_authenticate(user=remote_author_a)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
