import pytest
from rest_framework.test import APIClient
from rest_framework import status
from .factories import AuthorFactory
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
def setup_entries(author_a, author_b):
    entry_author_a_1 = EntryFactory(
        author=author_a, visibility='PUBLIC', is_deleted=False)
    entry_author_a_2 = EntryFactory(
        author=author_a, visibility='UNLISTED', is_deleted=False)
    entry_author_a_3 = EntryFactory(
        author=author_a, visibility='FRIENDS', is_deleted=False)
    entry_author_a_4 = EntryFactory(
        author=author_a, visibility='PUBLIC', is_deleted=False)

    return (
        entry_author_a_1, entry_author_a_2,
        entry_author_a_3, entry_author_a_4
    )


@pytest.mark.django_db
class TestProfilePageAPI:

    def test_edit_profile(self, api_client, author_a):
        api_client.force_authenticate(user=author_a)
        url = f"/api/authors/{author_a.serial}/"
        updates = {
            "displayName": "Updated Name",
            "github": "https://github.com/updateduser",
            "profileImage": "https://example.com/updated.jpg"
        }

        response = api_client.patch(url, updates, format="json")
        assert response.status_code == status.HTTP_200_OK

        author_a.refresh_from_db()

        assert author_a.display_name == updates["displayName"]
        assert author_a.github == updates["github"]
        assert author_a.profile_image == updates["profileImage"]

    def test_profile_page(self, api_client, author_a, author_b, setup_entries):

        api_client.force_authenticate(user=author_b)
        url = f'/api/authors/{author_a.serial}/entries/'
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        returned_entries = data['src']

        public_entries = []
        for entry in setup_entries:
            if entry.visibility == 'PUBLIC':
                public_entries.append(entry)

        public_entries = sorted(
            public_entries, key=lambda entry: entry.published, reverse=True)

        assert len(returned_entries) == len(public_entries)

        i = 0
        for entry in returned_entries:
            assert (entry['id'].split('/')[-1] ==
                    str(public_entries[i].serial))
            i += 1
