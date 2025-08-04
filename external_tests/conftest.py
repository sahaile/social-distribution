import pytest
import requests
import threading
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


@pytest.fixture(scope="session")
def remote_server():
    """
    Fixture to run a simple HTTP server in a background thread.
    This server acts as a controllable "remote" node for testing federation.
    """
    class RemoteAuthorHandler(BaseHTTPRequestHandler):
        # Class-level variable to store the response data
        _response_data = (b'{}', 200, {'Content-Type': 'application/json'})

        @classmethod
        def set_response(cls, body, status_code=200, headers=None):
            """Sets the response for the next GET request."""
            if headers is None:
                headers = {'Content-Type': 'application/json'}
            cls._response_data = (
                json.dumps(body).encode('utf-8'),
                status_code,
                headers)

        @classmethod
        def set_error_response(cls, status_code=500):
            """Sets a simple error response."""
            cls._response_data = (
                b'{}', status_code, {
                    'Content-Type': 'application/json'})

        def do_GET(self):
            body, status, headers = self.__class__._response_data
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # Suppress log messages to keep test output clean
            return

    # Find a free port
    with HTTPServer(("127.0.0.1", 0), RemoteAuthorHandler) as httpd:
        port = httpd.server_address[1]
        server_thread = threading.Thread(target=httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        # Yield the server address and the handler to control its responses
        yield (f"http://127.0.0.1:{port}", RemoteAuthorHandler)

        # Teardown: stop the server
        httpd.shutdown()
        server_thread.join()


@pytest.fixture
def authenticated_session(live_server):
    """
    A fixture factory that returns a function to create a logged-in
    requests.Session for a given user.
    """
    def _authenticated_session(user, password='password123'):
        # 1. Start a session
        session = requests.Session()

        # 2. Get the login page to get a CSRF token
        login_url = f'{live_server.url}/login/'
        session.get(login_url)
        # Find the CSRF token cookie (may be named csrftoken_default,
        # csrftoken_node1, etc.)
        csrf_cookie_name = None
        csrf_token = None
        for cookie_name in session.cookies.keys():
            if cookie_name.startswith('csrftoken'):
                csrf_cookie_name = cookie_name
                csrf_token = session.cookies[cookie_name]
                break
        # Check that a CSRF token cookie was found
        assert csrf_cookie_name is not None, (
            "No CSRF token found in cookies: "
            f"{list(session.cookies.keys())}"
        )

        # 3. Log in to get a session id
        login_data = {
            'username': user.username,
            'password': password,
            'csrfmiddlewaretoken': csrf_token
        }
        login_response = session.post(
            login_url,
            data=login_data,
            headers={'Referer': login_url}
        )

        # A successful login should result in a sessionid cookie
        login_response.raise_for_status()
        # Find the session cookie (may be named sessionid_default,
        # sessionid_node1, etc.)
        session_cookie_exists = any(cookie_name.startswith(
            'sessionid') for cookie_name in session.cookies.keys())
        assert session_cookie_exists, f"No session cookie found in cookies: {
            list(
                session.cookies.keys())}"

        # Get the current CSRF token from cookies after login
        current_csrf_token = None
        for cookie_name in session.cookies.keys():
            if cookie_name.startswith('csrftoken'):
                current_csrf_token = session.cookies[cookie_name]
                break

        # Set the CSRF token and Referer for subsequent requests
        session.headers.update({
            'X-CSRFToken': current_csrf_token,
            'Referer': live_server.url
        })

        return session

    return _authenticated_session


@pytest.fixture
def created_authors(db, live_server):
    """
    Fixture to create a set of authors for testing.
    """
    from authors.models import Author
    import uuid

    authors_data = [
        {
            'username': f'testuser{i}',
            'displayName': f'Test User {i}',
            'github': f'http://github.com/testuser{i}'
        } for i in range(1, 6)
    ]

    created = []
    for data in authors_data:
        # Generate unique serial for each author
        serial = str(uuid.uuid4())
        author = Author.objects.create_user(
            username=data['username'],
            password='password123'
        )
        author.display_name = data['displayName']
        author.github = data['github']
        author.host = live_server.url + "/api/"
        author.serial = serial
        # Generate unique URL based on host and serial
        author.url = f"{author.host}authors/{serial}/"
        author.save()
        created.append(author)
    return created


@pytest.fixture
def remote_authors(db):
    """
    Fixture to create remote authors for testing federation.
    """
    from authors.models import Author
    import uuid

    remote_authors_data = []

    for i in range(1, 6):
        serial = str(uuid.uuid4())
        remote_authors_data.append(
            {
                'username': f'remoteuser{i}',
                'password': 'password123',
                'displayName': f'Remote User {i}',
                'github': f'http://github.com/testuser{i}',
                'serial': serial,
                'host': f'remote_host_{i}.com/api/',
                'url': f'remote_host_{i}.com/api/authors/{serial}/',
            }
        )

    created = []
    for remote_author in remote_authors_data:
        author, _ = Author.objects.get_or_create(
            url=remote_author['url'],
            defaults={
                'serial': remote_author['serial'],
                'host': remote_author['host'],
                'display_name': remote_author['displayName'],
                'github': remote_author['github'],
                'profile_image': remote_author.get('profileImage', ''),
                # Remote authors are not active users on this system
                'is_active': False,
                # Ensure username is unique
                'username': f"proxy_{uuid.uuid4()}",
            }
        )
        created.append(author)

    return created


@pytest.fixture
def created_entries(db, live_server, created_authors):
    from entries.models import Entry, VISIBILITY_CHOICES
    import random

    created = []
    for i in range(10):
        new_entry = Entry(title=f"Random test title {i}",
                          description="Description for test entry #{i}",
                          content="",
                          content_type="text/plain",
                          author=random.choice(created_authors),
                          visibility=random.choice(VISIBILITY_CHOICES)[0],)
        new_entry.save()
        created.append(new_entry)
    return created
