import pytest
from rest_framework.test import APIClient
from authors.tests.factories import (
    AuthorFactory,
    FollowFactory,
    RemoteAuthorFactory,
    RemoteNodeFactory,
)
from .factories import EntryFactory
from rest_framework import status
from datetime import datetime


""" Local Testing """


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
def setup_entries(author_a, author_b):
    entry_author_a_1 = EntryFactory(
        author=author_a, visibility='PUBLIC', is_deleted=False)
    entry_author_a_2 = EntryFactory(
        author=author_a, visibility='UNLISTED', is_deleted=False)
    entry_author_a_3 = EntryFactory(
        author=author_a, visibility='FRIENDS', is_deleted=False)
    entry_author_a_4 = EntryFactory(
        author=author_a, visibility='PUBLIC', is_deleted=True)

    entry_author_b_1 = EntryFactory(
        author=author_b, visibility='PUBLIC', is_deleted=False)
    entry_author_b_2 = EntryFactory(
        author=author_b, visibility='UNLISTED', is_deleted=False)
    entry_author_b_3 = EntryFactory(
        author=author_b, visibility='FRIENDS', is_deleted=False)
    entry_author_b_4 = EntryFactory(
        author=author_b, visibility='PUBLIC', is_deleted=True)

    return (
        entry_author_a_1, entry_author_a_2,
        entry_author_a_3, entry_author_a_4,
        entry_author_b_1, entry_author_b_2,
        entry_author_b_3, entry_author_b_4
    )


@pytest.mark.django_db
class TestEntryListAPI:

    # Will show all entries of author_b except if deleted. author_a and
    # author_b are friends.
    def test_entry_list_when_friends(
            self, api_client, author_a, author_b, setup_entries):

        (
            entry_author_a_1, entry_author_a_2,
            entry_author_a_3, entry_author_a_4,
            entry_author_b_1, entry_author_b_2,
            entry_author_b_3, entry_author_b_4
        ) = setup_entries

        FollowFactory.create_accepted(follower=author_a, following=author_b)
        FollowFactory.create_accepted(
            follower=author_b, following=author_a)

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # check if entries are in order from newest to oldest (sorted with the
        # most recent entries first.)
        sorted_entries = sorted(entries, key=lambda entry:
                                datetime.fromisoformat(
                                    entry['published']), reverse=True)
        sorted_entry_ids = [entry['id'].split(
            '/')[-1] for entry in sorted_entries]
        assert entry_ids == sorted_entry_ids

        # assert author_a can see their own PUBLIC, UNLISTED, FRIENDS
        # entries
        assert str(entry_author_a_1.serial) in entry_ids
        assert str(entry_author_a_2.serial) in entry_ids
        assert str(entry_author_a_3.serial) in entry_ids

        # cannot see deleted entries
        assert str(entry_author_a_4.serial) not in entry_ids

        url = f'/api/authors/{author_b.serial}/entries/'
        response = api_client.get(url)

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # assert author_a can see author_b's PUBLIC, UNLISTED, and FRIENDS
        # entries
        assert str(entry_author_b_1.serial) in entry_ids
        assert str(entry_author_b_2.serial) in entry_ids
        assert str(entry_author_b_3.serial) in entry_ids

        # cannot see deleted entries in stream
        assert str(entry_author_b_4.serial) not in entry_ids

    # Will show only public entries of author_b except if deleted. author_a
    # and author_b are not following each other.

    def test_entry_list_when_not_following(
            self, api_client, author_a, author_b, setup_entries):
        (
            entry_author_a_1, entry_author_a_2,
            entry_author_a_3, entry_author_a_4,
            entry_author_b_1, entry_author_b_2,
            entry_author_b_3, entry_author_b_4
        ) = setup_entries

        FollowFactory.create_rejected(follower=author_a, following=author_b)
        FollowFactory.create_rejected(follower=author_b, following=author_a)

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # check if entries are in order from newest to oldest (sorted with the
        # most recent entries first.)
        sorted_entries = sorted(entries, key=lambda entry:
                                datetime.fromisoformat(
                                    entry['published']), reverse=True)
        sorted_entry_ids = [entry['id'].split(
            '/')[-1] for entry in sorted_entries]
        assert entry_ids == sorted_entry_ids

        # assert author_a can see their own PUBLIC, UNLISTED, FRIENDS entries
        assert str(entry_author_a_1.serial) in entry_ids
        assert str(entry_author_a_2.serial) in entry_ids
        assert str(entry_author_a_3.serial) in entry_ids

        # cannot see deleted entries
        assert str(entry_author_a_4.serial) not in entry_ids

        url = f'/api/authors/{author_b.serial}/entries/'
        response = api_client.get(url)

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # cannot see non-public entries from author_b
        assert str(entry_author_b_1.serial) in entry_ids
        assert str(entry_author_b_2.serial) not in entry_ids
        assert str(entry_author_b_3.serial) not in entry_ids

        # cannot see deleted entries in stream
        assert str(entry_author_b_4.serial) not in entry_ids

    # Will show only public and unlisted entries of author_b except if
    # deleted. author_a is following author_b but not vice versa.

    def test_entry_list_when_following_but_not_friends(
            self, api_client, author_a, author_b, setup_entries):
        (
            entry_author_a_1, entry_author_a_2,
            entry_author_a_3, entry_author_a_4,
            entry_author_b_1, entry_author_b_2,
            entry_author_b_3, entry_author_b_4
        ) = setup_entries

        FollowFactory.create_accepted(follower=author_a, following=author_b)

        api_client.force_authenticate(user=author_a)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # check if entries are in order from newest to oldest (sorted with the
        # most recent entries first.)
        sorted_entries = sorted(entries, key=lambda entry:
                                datetime.fromisoformat(
                                    entry['published']), reverse=True)
        sorted_entry_ids = [entry['id'].split(
            '/')[-1] for entry in sorted_entries]
        assert entry_ids == sorted_entry_ids

        # assert author_a can see their own PUBLIC, UNLISTED, FRIENDS
        # entries
        assert str(entry_author_a_1.serial) in entry_ids
        assert str(entry_author_a_2.serial) in entry_ids
        assert str(entry_author_a_3.serial) in entry_ids

        # cannot see deleted entries
        assert str(entry_author_a_4.serial) not in entry_ids

        url = f'/api/authors/{author_b.serial}/entries/'
        response = api_client.get(url)

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # assert author_a can see author_b's PUBLIC and UNLISTED entries
        # only
        assert str(entry_author_b_1.serial) in entry_ids
        assert str(entry_author_b_2.serial) in entry_ids
        assert str(entry_author_b_3.serial) not in entry_ids

        # cannot see deleted entries in stream
        assert str(entry_author_b_4.serial) not in entry_ids

    # Updates an entry and makes sure it returns the updated content of the
    # entry
    def test_edited_entry(
            self, api_client, author_a):

        api_client.force_authenticate(user=author_a)

        entry_author_a_1 = EntryFactory(
            author=author_a, visibility='PUBLIC', is_deleted=False)

        entry_author_a_1.title = "Title A1"
        entry_author_a_1.content = "Content A1"
        entry_author_a_1.save()

        assert entry_author_a_1.title == "Title A1"
        assert entry_author_a_1.published != entry_author_a_1.updated

        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        updated_entry_id = str(entry_author_a_1.serial)

        assert updated_entry_id in entry_ids

        i = 0
        for id in entry_ids:
            if id == updated_entry_id:
                print(entries)
                assert entries[i]['title'] == "Title A1"
                break
            i += 1


""" Remote Testing """


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


@pytest.fixture
def setup_entries_with_remote(local_author_a, remote_author_a):
    # Entries for local author
    entry_local_public = EntryFactory(
        author=local_author_a,
        visibility='PUBLIC',
        is_deleted=False)
    entry_local_unlisted = EntryFactory(
        author=local_author_a,
        visibility='UNLISTED',
        is_deleted=False)
    entry_local_friends = EntryFactory(
        author=local_author_a,
        visibility='FRIENDS',
        is_deleted=False)
    entry_local_deleted = EntryFactory(
        author=local_author_a,
        visibility='PUBLIC',
        is_deleted=True)

    # Entries for remote author
    entry_remote_public = EntryFactory(
        author=remote_author_a,
        visibility='PUBLIC',
        is_deleted=False)
    entry_remote_unlisted = EntryFactory(
        author=remote_author_a,
        visibility='UNLISTED',
        is_deleted=False)
    entry_remote_friends = EntryFactory(
        author=remote_author_a,
        visibility='FRIENDS',
        is_deleted=False)
    entry_remote_deleted = EntryFactory(
        author=remote_author_a,
        visibility='PUBLIC',
        is_deleted=True)

    return (
        entry_local_public, entry_local_unlisted,
        entry_local_friends, entry_local_deleted,
        entry_remote_public, entry_remote_unlisted,
        entry_remote_friends, entry_remote_deleted
    )


@pytest.mark.django_db
class TestRemoteEntryListAPI:

    # Will show only public entries of local_author_a except if deleted.
    # local_author_a and remote_author_a are not following each other.

    def test_entry_list_when_not_following(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b,
            setup_entries_with_remote):
        (
            entry_local_public, entry_local_unlisted,
            entry_local_friends, entry_local_deleted,
            entry_remote_public, entry_remote_unlisted,
            entry_remote_friends, entry_remote_deleted
        ) = setup_entries_with_remote

        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        api_client.force_authenticate(user=local_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # check if entries are in order from newest to oldest (sorted with the
        # most recent entries first.)
        sorted_entries = sorted(entries, key=lambda entry:
                                datetime.fromisoformat(
                                    entry['published']), reverse=True)
        sorted_entry_ids = [entry['id'].split(
            '/')[-1] for entry in sorted_entries]
        assert entry_ids == sorted_entry_ids

        # assert author_a can see their own PUBLIC, UNLISTED, FRIENDS entries
        assert str(entry_local_public.serial) in entry_ids
        assert str(entry_local_unlisted.serial) in entry_ids
        assert str(entry_local_friends.serial) in entry_ids

        # cannot see deleted entries
        assert str(entry_local_deleted.serial) not in entry_ids

        url = f'/api/authors/{remote_author_a.serial}/entries/'
        response = api_client.get(url)

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # cannot see non-public entries from author_b
        assert str(entry_remote_public.serial) in entry_ids
        assert str(entry_remote_unlisted.serial) not in entry_ids
        assert str(entry_remote_friends.serial) not in entry_ids

        # cannot see deleted entries in stream
        assert str(entry_remote_deleted.serial) not in entry_ids

    # Will show all entries of remote_author_a except if deleted.
    # local_author_a and remote_author_a are friends.
    def test_entry_list_when_friends(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b,
            setup_entries_with_remote):
        (
            entry_local_public, entry_local_unlisted,
            entry_local_friends, entry_local_deleted,
            entry_remote_public, entry_remote_unlisted,
            entry_remote_friends, entry_remote_deleted
        ) = setup_entries_with_remote

        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        FollowFactory.create_accepted(
            follower=remote_author_a,
            following=local_author_a)
        FollowFactory.create_accepted(
            follower=local_author_a, following=remote_author_a)

        api_client.force_authenticate(user=local_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # check if entries are in order from newest to oldest (sorted with the
        # most recent entries first.)
        sorted_entries = sorted(entries, key=lambda entry:
                                datetime.fromisoformat(
                                    entry['published']), reverse=True)
        sorted_entry_ids = [entry['id'].split(
            '/')[-1] for entry in sorted_entries]
        assert entry_ids == sorted_entry_ids

        # assert author_a can see their own PUBLIC, UNLISTED, FRIENDS
        # entries
        assert str(entry_local_public.serial) in entry_ids
        assert str(entry_local_unlisted.serial) in entry_ids
        assert str(entry_local_friends.serial) in entry_ids

        # cannot see deleted entries
        assert str(entry_local_deleted.serial) not in entry_ids

        url = f'/api/authors/{remote_author_a.serial}/entries/'
        response = api_client.get(url)

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # assert author_a can see author_b's PUBLIC, UNLISTED, and FRIENDS
        # entries
        assert str(entry_remote_public.serial) in entry_ids
        assert str(entry_remote_unlisted.serial) in entry_ids
        assert str(entry_remote_friends.serial) in entry_ids

        # cannot see deleted entries in stream
        assert str(entry_remote_deleted.serial) not in entry_ids

    # Will show only public and unlisted entries of remote_author_a except if
    # deleted. local_author_a is following remote_author_a but not vice versa.

    def test_entry_list_when_following_but_not_friends(
            self,
            api_client,
            local_author_a,
            local_author_b,
            remote_author_a,
            remote_author_b,
            setup_entries_with_remote):
        (
            entry_local_public, entry_local_unlisted,
            entry_local_friends, entry_local_deleted,
            entry_remote_public, entry_remote_unlisted,
            entry_remote_friends, entry_remote_deleted
        ) = setup_entries_with_remote

        # This is an entry that will show up in all the streams of all the
        # authors on all the nodes where I have at least one follower.
        FollowFactory.create_accepted(
            follower=local_author_b,
            following=remote_author_a)
        FollowFactory.create_accepted(
            follower=remote_author_b,
            following=local_author_a)

        FollowFactory.create_accepted(
            follower=local_author_a,
            following=remote_author_a)

        api_client.force_authenticate(user=local_author_a)
        url = f'/api/authors/{local_author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # check if entries are in order from newest to oldest (sorted with the
        # most recent entries first.)
        sorted_entries = sorted(entries, key=lambda entry:
                                datetime.fromisoformat(
                                    entry['published']), reverse=True)
        sorted_entry_ids = [entry['id'].split(
            '/')[-1] for entry in sorted_entries]
        assert entry_ids == sorted_entry_ids

        # assert author_a can see their own PUBLIC, UNLISTED, FRIENDS
        # entries
        assert str(entry_local_public.serial) in entry_ids
        assert str(entry_local_unlisted.serial) in entry_ids
        assert str(entry_local_friends.serial) in entry_ids

        # cannot see deleted entries
        assert str(entry_local_deleted.serial) not in entry_ids

        url = f'/api/authors/{remote_author_a.serial}/entries/'
        response = api_client.get(url)

        entries = [entry for entry in response.data['src']]
        entry_ids = [entry['id'].split('/')[-1] for entry in entries]

        # assert author_a can see author_b's PUBLIC and UNLISTED entries
        # only
        assert str(entry_remote_public.serial) in entry_ids
        assert str(entry_remote_unlisted.serial) in entry_ids
        assert str(entry_remote_friends.serial) not in entry_ids

        # cannot see deleted entries in stream
        assert str(entry_remote_deleted.serial) not in entry_ids
