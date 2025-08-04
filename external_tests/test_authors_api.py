import pytest
import requests
from rest_framework import status

# Pytest mark for all tests in this file
pytestmark = pytest.mark.django_db


class TestAuthorsAPI:
    """
    Tests for the /api/authors/ endpoint.
    """

    def test_get_authors_list(self, live_server, created_authors):
        """
        Tests GET /api/authors/
        Should retrieve all profiles on the node.
        """
        url = f'{live_server.url}/api/authors/'
        response = requests.get(url)

        assert response.status_code == status.HTTP_200_OK

        response_json = response.json()
        assert response_json['type'] == 'authors'

        # In the default, unpaginated view, all authors should be returned
        assert len(response_json['authors']) == len(created_authors)

        # Check for expected fields in the first author
        first_author = response_json['authors'][0]
        assert 'type' in first_author and first_author['type'] == 'author'
        assert 'id' in first_author
        assert 'host' in first_author
        assert 'displayName' in first_author
        assert 'github' in first_author
        assert 'profileImage' in first_author

    def test_get_authors_paginated(self, live_server, created_authors):
        """
        Tests GET /api/authors/ with pagination.
        """
        base_url = f'{live_server.url}/api/authors/'

        # Test Case 1: Get first page, size 2
        url = f'{base_url}?page=1&size=2'
        response = requests.get(url)
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json['authors']) == 2

        # Verify displayNames to ensure we have the first two authors
        display_names = {author['displayName']
                         for author in response_json['authors']}
        expected_names = {'Test User 1', 'Test User 2'}
        assert display_names == expected_names

        # Test Case 2: Get second page, size 2
        url = f'{base_url}?page=2&size=2'
        response = requests.get(url)
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json['authors']) == 2
        display_names = {author['displayName']
                         for author in response_json['authors']}
        expected_names = {'Test User 3', 'Test User 4'}
        assert display_names == expected_names

        # Test Case 3: Get third page, size 2 (should only have 1 remaining)
        url = f'{base_url}?page=3&size=2'
        response = requests.get(url)
        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        assert len(response_json['authors']) == 1
        display_names = {author['displayName']
                         for author in response_json['authors']}
        expected_names = {'Test User 5'}
        assert display_names == expected_names

    def test_get_authors_pagination_page_not_found(
            self, live_server, created_authors):
        """
        Tests GET /api/authors/ for a page that does not exist.
        A page number that is too high, negative,
        or malformed should return a 404.
        """
        # Page too high
        url = f'{live_server.url}/api/authors/?page=100&size=2'
        response = requests.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Page -1
        url = f'{live_server.url}/api/authors/?page=-1&size=2'
        response = requests.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Malformed page parameter
        url = f'{live_server.url}/api/authors/?page=abc&size=2'
        response = requests.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
