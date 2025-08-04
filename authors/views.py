from rest_framework import generics, status, filters
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from authors.services import NodeService
from entries.models import VISIBILITY_CHOICES
from entries.serializers import EntrySerializer
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import (
    extend_schema, OpenApiResponse, OpenApiExample, inline_serializer,
    OpenApiParameter
)
from rest_framework import serializers
from .permissions import IsAuthenticatedOrReadOnlyForPublic
from entries.models import Entry, Comment, Like
from entries.serializers import (
    CommentSerializer, LikeSerializer,
    PaginatedCommentSerializer,
    PaginatedLikeSerializer
)
from .utils import (
    get_author_from_identifier,
    RemoteConnectionError,
    get_object_from_fqid,
)
import urllib.parse
from django.http import Http404
from rest_framework.permissions import IsAuthenticated
import requests
from django.db.models import Q
import uuid
from django.views.generic import TemplateView
from .serializers import (
    AuthorSerializer, FollowSerializer, FollowersListSerializer,
    AuthorsListSerializer, FollowingListSerializer,
    RemoteAuthorValidationSerializer, FriendsListSerializer
)
from .models import Follow
from .authentication import RemoteNodeAuthentication
from .utils import get_or_create_proxy_author
from requests.auth import HTTPBasicAuth
from .models import RemoteNode
from rest_framework.authentication import (
    SessionAuthentication, BasicAuthentication
)
from .permissions import IsAuthenticatedOrRemoteNodeOrReadOnly
from .permissions import CanPostToInbox
from django.core.exceptions import ValidationError
import logging
logging.basicConfig(level=logging.DEBUG)

# Use the Author model consistently via get_user_model()
Author = get_user_model()


class StandardPagination(PageNumberPagination):
    page_size_query_param = 'size'
    page_size = 10
    max_page_size = 100


@extend_schema(
    summary="List All Authors",
    description=(
        """
        ### When to Use
        Use this endpoint to get a list of all author profiles registered on
        the local node. It's useful for discovery, such as searching for
        authors or displaying a directory.

        ### How to Use
        - This is a public endpoint; no authentication is required.
        - The response is paginated. Use the `?page=<number>` and
          `?size=<number>` query parameters to navigate through the list.
        - Invalid pagination parameters (e.g., non-integer page, page out of
          range) will result in a `404 Not Found` response.

        ### Why/Why Not
        - **Why**: Provides a simple way to see all users on the server.
        - **Why Not**: For large systems, this list could be very long.
          In a federated context, this only shows local authors.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=AuthorsListSerializer,
            description=(
                "A paginated list of authors was successfully retrieved."
            ),
            examples=[
                OpenApiExample(
                    "Successful Response",
                    value={
                        "type": "authors",
                        "authors": [
                            {
                                "type": "author",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "cfe65120-7091-4131-bea8-9d36bab2d40b"
                                ),
                                "host": "http://127.0.0.1:8000/",
                                "displayName": "b",
                                "github": "",
                                "profileImage": "",
                                "web": (
                                    "http://127.0.0.1:8000/authors/"
                                    "cfe65120-7091-4131-bea8-9d36bab2d40b"
                                ),
                                "followers_count": 0,
                                "following_count": 0
                            },
                            {
                                "type": "author",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "e3eaa614-17db-418a-ac33-873dc155d9bc"
                                ),
                                "host": "http://127.0.0.1:8000/",
                                "displayName": "d",
                                "github": "http://github.com/d",
                                "profileImage": "https://i.imgur.com/a.png",
                                "web": (
                                    "http://127.0.0.1:8000/authors/"
                                    "e3eaa614-17db-418a-ac33-873dc155d9bc"
                                ),
                                "followers_count": 0,
                                "following_count": 0
                            }
                        ]
                    }
                )
            ]
        ),
        404: OpenApiResponse(
            description=(
                "Not Found. The requested page does not exist or the "
                "pagination parameters are invalid."
            )
        ),
    },
    parameters=[
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description='A page number within the paginated result set.'
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Number of results to return per page.'
        ),
    ],
    tags=['Authors']
)
class AuthorListView(generics.ListAPIView):
    """
    List all authors that this node knows about.
    This includes local authors and any remote authors that have been
    discovered through federation.
    """
    queryset = Author.objects.filter(is_active=True)
    serializer_class = AuthorSerializer
    pagination_class = StandardPagination
    authentication_classes = [RemoteNodeAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticatedOrRemoteNodeOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ['display_name']

    def get_queryset(self):
        """
        Return all authors that should be discoverable:
        - For remote node requests: only local authors
        (prevents proxy recursion)
        - For local user requests: local authors + remote
        proxy authors (for search)
        """
        # Build current host from the request
        current_host = f"{self.request.scheme}://{self.request.get_host()}/"

        # Check if request is from a remote node
        if isinstance(getattr(self.request, 'user', None), RemoteNode):
            # Remote nodes should only get local authors to prevent proxy
            # recursion
            return Author.objects.filter(is_active=True, host=current_host)

        # Local users get both local active authors AND remote proxy authors
        return Author.objects.filter(
            Q(is_active=True, host=current_host) |  # Local active authors
            # Remote authors (any host != current)
            Q(host__isnull=False) & ~Q(host=current_host)
        )

    def _fetch_remote_authors(self):
        """
        Iterate through all active remote nodes and fetch their author lists.
        This will populate our database with proxy objects for remote authors.
        """
        remote_nodes = RemoteNode.objects.filter(is_active=True)
        logging.debug(
            f"Fetching remote authors from {len(remote_nodes)} nodes.")
        for node in remote_nodes:
            try:
                auth = HTTPBasicAuth(
                    node.outgoing_username,
                    node.outgoing_password)
                response = requests.get(
                    f"{node.host}/api/authors/",
                    auth=auth,
                    headers={'Accept': 'application/json'},
                    timeout=5
                )
                response.raise_for_status()
                authors_data = response.json()

                for author_data in authors_data.get('authors', []):
                    # Use our utility to create proxy authors. This will
                    # either create a new proxy or update an existing one.
                    try:
                        logging.debug(
                            f"Getting/Creating proxy author: "
                            f"{author_data['displayName']}")
                        get_or_create_proxy_author(author_data, self.request)
                    except Exception as e:
                        logging.warning(
                            "Exception while getting/creating proxy author "
                            "(%s): %s",
                            author_data["id"],
                            e
                        )

            except requests.exceptions.RequestException:
                logging.warning(
                    "RequestException while fetching remote authors: %s",
                    node.host)
            except Exception as e:
                logging.warning(
                    "Exception while fetching remote authors: %s. %s",
                    node.host, e)

    def list(self, request, *args, **kwargs):
        # Only fetch remote authors if the request is from a
        # local user (not a remote node).
        # This check prevents an infinite loop where nodes continuously ask
        # each other for authors.
        if not isinstance(request.user, RemoteNode):
            logging.debug("Fetching remote authors for local user request.")
            self._fetch_remote_authors()
        else:
            logging.debug("Serving remote node request.")

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response({'type': 'authors', 'authors': serializer.data})

        serializer = self.get_serializer(queryset, many=True)
        return Response({'type': 'authors', 'authors': serializer.data})


@extend_schema(
    summary="Get or Update an Author's Profile",
    description=(
        """
        ### Functionality
        This endpoint serves multiple purposes:
        - **GET**: Retrieve the public profile of a specific author
          (local or remote via proxy).
        - **PUT/PATCH**: Update an author's profile with different
          permission levels.

        ### URL Pattern
        - **Local**: `://service/api/authors/{AUTHOR_SERIAL}/`
          - GET: retrieve AUTHOR_SERIAL's profile
          - PUT: update AUTHOR_SERIAL's profile
            (authenticated users or remote nodes)
          - PATCH: update AUTHOR_SERIAL's profile
            (authenticated users or remote nodes)

        *Remote author lookup via FQID is supported via proxy.*

        ### When to Use
        - Use **GET** to view any author's profile page.
        - Use **PUT** or **PATCH** to update author profiles:
          - Local users can update their own profiles
          - Remote nodes can update proxy author records for their own authors

        ### How to Use
        - The `serial_or_fqid` parameter can be a local author's UUID
          serial or remote FQID.
        - **GET** is a public endpoint.
        - **PUT/PATCH** requires authentication:
          - Local users: can only update their own profile
          - Remote nodes: can update proxy authors from their own node
          - Attempting to update unauthorized profiles results in
            `403 Forbidden`

        ### Request Body (for PUT/PATCH)
        Provide the fields you want to update.
        - `displayName` (string)
        - `github` (URL string)
        - `profileImage` (URL string)

        ### Author Update Federation
        When a local author's profile is updated, the changes are automatically
        propagated to remote nodes where the author has followers, ensuring
        distributed profile consistency.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=AuthorSerializer,
            description=(
                "The author's profile was successfully retrieved or updated."
            ),
            examples=[
                OpenApiExample(
                    "Successful GET/Update Response",
                    value={
                        "type": "author",
                        "id": (
                            "http://127.0.0.1:8000/api/authors/"
                            "02fd97c2-f816-4e17-ab4f-6ee560cd12fa"
                        ),
                        "host": "http://127.0.0.1:8000/",
                        "displayName": "b",
                        "github": "https://github.com/newgithub",
                        "profileImage": "https://example.com/new-image.png",
                        "web": (
                            "http://127.0.0.1:8000/authors/"
                            "02fd97c2-f816-4e17-ab4f-6ee560cd12fa"
                        ),
                        "followers_count": 0,
                        "following_count": 0
                    }
                )
            ]
        ),
        400: OpenApiResponse(
            description=(
                "Bad Request. The request body was invalid. This can happen "
                "if a required field is missing for a PUT request, or if a "
                "field value is malformed (e.g., an invalid URL for "
                "'github')."
            )
        ),
        401: OpenApiResponse(
            description=(
                "Unauthorized. Authentication credentials were not provided "
                "for a PUT or PATCH request."
            )
        ),
        403: OpenApiResponse(
            description=(
                "Forbidden. You do not have permission to update this "
                "author's profile. You can only update your own."
            )
        ),
        404: OpenApiResponse(
            description=(
                "Not Found. An author with the specified UUID was not found."
            )
        )
    },
    examples=[
        OpenApiExample(
            "Update Request Body",
            value={
                "displayName": "New Display Name",
                "github": "https://github.com/newgithub",
                "profileImage": "https://example.com/new-image.png"
            },
            request_only=True
        ),
    ],
    tags=['Authors']
)
class AuthorDetailView(generics.RetrieveUpdateAPIView):
    """
    API view for retrieving (GET) and updating (PUT, PATCH) a single author.
    - GET: If the author is local, it returns their profile. If the author is
      remote, it acts as a proxy and fetches their profile from the remote
      node.
    - PUT/PATCH: Local authors can be updated by users, remote proxy authors
      can be updated by their authoritative nodes.
    """
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    authentication_classes = [
        RemoteNodeAuthentication,
        BasicAuthentication,
        SessionAuthentication]
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    # Use the 'serial' from the URL
    lookup_field = 'serial_or_fqid'
    lookup_url_kwarg = 'serial_or_fqid'

    def get_object(self):
        """
        Override get_object to use our helper that can handle FQIDs.
        This method is primarily used for the 'update' part of the view,
        as the 'retrieve' part is handled separately to support proxying.
        """
        serial_or_fqid = self.kwargs[self.lookup_url_kwarg]
        author = get_author_from_identifier(serial_or_fqid, self.request)

        # If it's a remote FQID string, we can't update it.
        if isinstance(author, str):
            raise Http404(
                "Cannot update a remote author. "
                "This endpoint only supports updating local authors."
            )

        # Ensure the user has permission to update this object.
        self.check_object_permissions(self.request, author)
        return author

    def retrieve(self, request, *args, **kwargs):
        """
        Handle GET requests.
        Identifies if the author is local or remote and acts accordingly.
        """
        serial_or_fqid = self.kwargs[self.lookup_url_kwarg]
        author_or_fqid = get_author_from_identifier(serial_or_fqid, request)

        # Case 1: The identifier points to a local author.
        if isinstance(author_or_fqid, Author):
            serializer = self.get_serializer(author_or_fqid)
            return Response(serializer.data)

        # Case 2: The identifier is a remote FQID string. Act as a proxy.
        elif isinstance(author_or_fqid, str):
            remote_url = author_or_fqid
            try:
                # TODO: Add authentication headers for remote requests
                # from other nodes.
                remote_response = requests.get(remote_url, timeout=5)
                remote_response.raise_for_status()
                response_json = remote_response.json()

                # Use the validation serializer to ensure the remote data
                # has the required structure before proxying.
                serializer = RemoteAuthorValidationSerializer(
                    data=response_json)
                serializer.is_valid(raise_exception=True)

                # Return the original, validated data
                return Response(
                    serializer.validated_data,
                    status=remote_response.status_code)
            except (
                requests.exceptions.RequestException,
                requests.exceptions.JSONDecodeError,
                serializers.ValidationError
            ) as e:
                raise RemoteConnectionError(
                    detail=f"Failed to retrieve or validate remote author: {e}"
                )

        # Fallback
        return Response(
            {"detail": "Invalid author identifier."},
            status=status.HTTP_400_BAD_REQUEST
        )

    def update(self, request, *args, **kwargs):
        """
        Handle author updates:
        - Local users can update their own profiles
        - Remote nodes can update proxy author records for their own authors
        """
        # Check if this is a request from a remote node
        if isinstance(request.user, RemoteNode):
            serial_or_fqid = self.kwargs[self.lookup_url_kwarg]

            # Try to get the author directly by serial
            try:
                author = Author.objects.get(serial=serial_or_fqid)
            except (Author.DoesNotExist, ValueError):
                raise Http404("Author not found")

            current_host = f"{request.scheme}://{request.get_host()}/"

            # Remote node can only update proxy authors from their own host
            if author.host and author.host != current_host:
                # Check if the requesting node is authorized for this author's
                # host
                author_host = author.host.rstrip('/') + '/'
                requesting_node_host = request.user.host.rstrip('/') + '/'

                if author_host == requesting_node_host:
                    # Allow the update of proxy author data
                    serializer = self.get_serializer(
                        author, data=request.data, partial=kwargs.get(
                            'partial', False))
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    return Response(serializer.data)
                else:
                    return Response(
                        {
                            "detail": (
                                "You can only update authors "
                                "from your own node."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                return Response(
                    {"detail": "Cannot update local authors."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # For local users, use the standard DRF flow
        return super().update(request, *args, **kwargs)


@extend_schema(
    summary="List an Author's Followers",
    description=(
        """
        ### When to Use
        Use this endpoint to get a list of authors who are following a
        specific author. This is useful for displaying a "Followers" list
        on a profile page.

        ### How to Use
        - This is a public endpoint.
        - It only returns followers whose follow request has been
          **Accepted**. Pending or rejected requests are not included.
        - The `serial` in the URL identifies the author whose
          followers you want to see.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=FollowersListSerializer,
            description=(
                "A list of followers was successfully retrieved."
            ),
            examples=[
                OpenApiExample(
                    "Successful Response with Followers",
                    value={
                        "type": "followers",
                        "followers": [
                            {
                                "type": "author",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "b3b4d03b-1b5f-5b7c-9b8f-4c7c5d4f4c7d"
                                ),
                                "host": "http://127.0.0.1:8000/",
                                "displayName": "John Follower",
                                "github": (
                                    "http://github.com/johnfollower"
                                ),
                                "profileImage": (
                                    "https://i.imgur.com/k7XVwpB.jpeg"
                                )
                            }
                        ]
                    }
                )
            ]
        )
    },
    tags=['Followers']
)
class FollowersListView(APIView):
    """
    GET /api/authors/{serial}/followers/ [local, remote]
    - get list of authors who are following this author
    """
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get(self, request, *args, **kwargs):
        author = get_object_or_404(Author, serial=self.kwargs['serial'])
        followers = author.get_followers()
        serializer = AuthorSerializer(
            followers, many=True, context={'request': request}
        )
        return Response({'type': 'followers', 'followers': serializer.data})


@extend_schema(
    summary="List Authors an Author is Following",
    description=(
        """
        ### When to Use
        Use this endpoint to see which other authors a specific author is
        following. This is useful for displaying a "Following" list on a
        profile page.

        ### How to Use
        - This is a public endpoint.
        - It only returns authors for whom the follow status is **Accepted**.
        - The `serial_or_fqid` in the URL identifies the author whose
          following list you want to see.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=FollowingListSerializer,
            description=(
                "A list of followed authors was successfully retrieved."
            ),
            examples=[
                OpenApiExample(
                    "Successful Response with Following",
                    value={
                        "type": "following",
                        "following": [
                            {
                                "type": "author",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "c4c5d04c-2c6f-6c8d-ac9f-5d8d6e5f5d8e"
                                ),
                                "host": "http://127.0.0.1:8000/",
                                "displayName": "Jane Followed",
                                "github": "http://github.com/janefollowed",
                                "profileImage": (
                                    "https://i.imgur.com/k7XVwpB.jpeg"
                                )
                            }
                        ]
                    }
                )
            ]
        )
    },
    tags=['Followers']
)
class FollowingListView(APIView):
    """
    GET /api/authors/{serial}/following/ [local, remote]
    - get list of authors this author is following
    """
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get(self, request, *args, **kwargs):
        author = get_author_from_identifier(self.kwargs['serial_or_fqid'])
        following = author.get_following()
        serializer = AuthorSerializer(
            following, many=True, context={'request': request}
        )
        return Response({'type': 'following', 'following': serializer.data})


@extend_schema(
    summary="List an Author's Friends (Mutual Followers)",
    description=(
        """
        ### When to Use
        Use this endpoint to get a list of authors who are mutual friends
        with a specific author (i.e., they both follow each other).

        ### How to Use
        - This is a public endpoint.
        - It only returns relationships where the follow status is
          **Accepted** in both directions.
        - The `serial` in the URL identifies the author whose
          friends you want to see.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=FriendsListSerializer,
            description="A list of friends was successfully retrieved.",
        )
    },
    tags=["Followers"],
)
class FriendsListView(APIView):
    """
    GET /api/authors/{serial}/friends/
    - get list of authors who are friends with this author (mutual follow)
    """

    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get(self, request, *args, **kwargs):
        author = get_object_or_404(Author, serial=self.kwargs["serial"])
        friends = author.get_friends()
        serializer = AuthorSerializer(
            friends, many=True, context={'request': request}
        )
        return Response({'type': 'friends', 'friends': serializer.data})


@extend_schema(
    summary="Manage a Specific Follower Relationship",
    description=(
        "This endpoint manages the relationship between a `follower` and a "
        "`followed` author. It has three methods:\n\n"
        "- **GET**: Check if `foreign_author_fqid` is a follower of "
        "`serial`.\n"
        "- **PUT**: Approve a follow request. The `followed` author approves "
        "the `follower`.\n"
        "- **DELETE**: An authenticated `follower` unfollows the `followed` "
        "author."
    ),
    tags=['Followers']
)
class FollowerDetailView(APIView):
    """
    GET /api/authors/{serial}/followers/{foreign_author_fqid}/ [local, remote]
    - check if foreign_author is following this author

    PUT /api/authors/{serial}/followers/{foreign_author_fqid}/ [local]
    - add foreign_author as follower (approve follow request)

    DELETE /api/authors/{serial}/followers/{foreign_author_fqid}/ [local]
    - remove foreign_author as follower
    """
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    @extend_schema(
        summary="Check if Following",
        description=(
            """
            ### When to Use
            Use this to verify if a specific follow relationship exists and is
            **Accepted**. For example, on a profile page, you could use this to
            determine if "User A is followed by User B".

            ### How to Use
            - `serial` is the author being followed.
            - `foreign_author_fqid` is the author who is potentially the
              follower.
            - The endpoint returns `200 OK` with the follower's author object
              if the relationship exists and is accepted.
            - It returns `404 Not Found` if the relationship does not exist,
              is pending, or has been rejected.
            """
        ),
        responses={
            200: AuthorSerializer,
            404: OpenApiResponse(
                description=(
                    "Not a follower, or the follow request is not in "
                    "'accepted' state."
                )
            )
        }
    )
    def get(self, request, *args, **kwargs):
        followed_author = get_object_or_404(
            Author, serial=kwargs['serial']
        )
        identifier = kwargs['foreign_author_fqid']

        try:
            # This function can return either an Author object or a URL string
            resolved_follower = get_author_from_identifier(identifier, request)
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # If the resolved follower is a string, it's a remote author URL.
        # We need to parse the UUID from it and find the local proxy object.
        if isinstance(resolved_follower, str):
            try:
                parsed_url = urllib.parse.urlparse(resolved_follower)
                follower_uuid = parsed_url.path.rstrip('/').split('/')[-1]
                # Now find the local proxy author object by its serial
                follower_author_obj = get_object_or_404(
                    Author, serial=follower_uuid
                )
            except (ValueError, IndexError):
                return Response(status=status.HTTP_404_NOT_FOUND)
        else:
            # It's already a local Author object
            follower_author_obj = resolved_follower

        # Now we can safely check the follow relationship
        if Follow.objects.filter(
            follower=follower_author_obj,
            following=followed_author,
            status=Follow.Status.ACCEPTED
        ).exists():
            serializer = AuthorSerializer(
                follower_author_obj, context={'request': request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(
                {"detail": "Foreign author is not following this author"},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        summary="Approve Follow Request",
        description=(
            """
            ### When to Use
            After a user has sent a follow request (via the Inbox), the
            recipient of that request uses this endpoint to approve it.

            ### How to Use
            - This is a **state-changing** action and requires authentication.
            - The authenticated user must be the author who is being followed
              (`serial`).
            - `foreign_author_fqid` is the author who sent the request.
            - A successful PUT changes the follow status from `PENDING` to
              `ACCEPTED`.
            - It will fail with `404 Not Found` if a pending request from that
              user doesn't exist.
            - It will fail with `403 Forbidden` if you try to approve a request
              for another user.
            """
        ),
        request=None,
        responses={
            200: AuthorSerializer,
            403: OpenApiResponse(
                description=(
                    "Permission denied. You can only approve requests made to "
                    "you."
                )
            ),
            404: OpenApiResponse(
                description=(
                    "No pending follow request found from this author."
                )
            )
        }
    )
    def put(self, request, *args, **kwargs):
        """Handle PUT requests for approving follow requests"""
        followed_author = get_object_or_404(Author, serial=kwargs['serial'])

        # The user must be authenticated and must be the one being followed
        if (request.user.is_anonymous or
                request.user.serial != followed_author.serial):
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            foreign_author_identifier = get_author_from_identifier(
                self.kwargs['foreign_author_fqid'], request)

            if isinstance(foreign_author_identifier, str):
                # It's a remote author FQID string. We need to find the local
                # proxy object that represents them.
                parsed_url = urllib.parse.urlparse(foreign_author_identifier)
                author_serial = parsed_url.path.rstrip('/').split('/')[-1]
                foreign_author = get_object_or_404(
                    Author, serial=author_serial)
            else:
                # It's a local author object.
                foreign_author = foreign_author_identifier
        except Http404:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Find and approve the follow request
        try:
            follow = Follow.objects.get(
                follower=foreign_author,
                following=followed_author
            )
            follow.approve()

            serializer = AuthorSerializer(
                foreign_author, context={
                    'request': request})
            return Response(serializer.data)
        except Follow.DoesNotExist:
            return Response(
                {"detail": "No follow request found from this author"},
                status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        summary="Unfollow an Author or Reject a Follow Request",
        description=(
            """
            ### When to Use
            This endpoint is used for two purposes:
            1.  An author can **unfollow** someone they are
            currently following.
            2.  An author can **reject** a pending follow request
            they have received.

            ### How to Use
            - This action requires authentication.
            - **To Unfollow**: The authenticated user must be the **follower**.
              They can delete the relationship regardless of its status.
              - `serial` is the author who was **followed**.
              - `foreign_author_fqid` is the author who was the **follower**
                (and is the authenticated user).
            - **To Reject**: The authenticated user must be the **followed**
              author. They can only delete the relationship if its status is
              `PENDING`.
              - `serial` is the author who was **followed** (and is the
                authenticated user).
              - `foreign_author_fqid` is the author who sent the request.
            - A successful DELETE removes the `Follow` record entirely.
            """
        ),
        responses={
            204: OpenApiResponse(
                description="The follow relationship was successfully deleted."
            ),
            403: OpenApiResponse(
                description="Permission denied. You are not authorized to "
                "perform this action."
            ),
            404: OpenApiResponse(
                description="Follow relationship not found."
            )
        }
    )
    def delete(self, request, *args, **kwargs):
        """Handle DELETE requests for unfollowing or rejecting requests."""
        followed_author = get_object_or_404(Author, serial=kwargs['serial'])

        try:
            foreign_author_identifier = get_author_from_identifier(
                self.kwargs['foreign_author_fqid'], request)

            if isinstance(foreign_author_identifier, str):
                # It's a remote author FQID string. We need to find the local
                # proxy object that represents them.
                parsed_url = urllib.parse.urlparse(foreign_author_identifier)
                author_serial = parsed_url.path.rstrip('/').split('/')[-1]
                follower_author = get_object_or_404(
                    Author, serial=author_serial)
            else:
                # It's a local author object.
                follower_author = foreign_author_identifier
        except (Http404, ValueError, IndexError):
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_authenticated:
            return Response(
                {"detail": "Authentication credentials were not provided."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            follow = Follow.objects.get(
                follower=follower_author, following=followed_author)
        except Follow.DoesNotExist:
            return Response(
                {"detail": "Follow relationship not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Permission checks
        is_follower = request.user.serial == follower_author.serial
        is_followed = request.user.serial == followed_author.serial

        # A follower can unfollow at any time.
        if is_follower:
            follow.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        # The followed author can reject a PENDING request.
        if is_followed:
            if follow.is_pending():
                follow.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            else:
                return Response(
                    {
                        "detail": (
                            "You can only reject a pending "
                            "follow request."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        return Response(
            {
                "detail": (
                    "You do not have permission to modify this relationship."
                )
            },
            status=status.HTTP_403_FORBIDDEN
        )


class AuthorProfilePageView(TemplateView):
    """
    Web page view for a single author's profile.
    Shows their entries based on the viewer's relationship to them.
    """
    template_name = 'authors/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. Get the author whose profile is being viewed
        author_to_view = get_object_or_404(
            Author, serial=self.kwargs['serial']
        )
        context['profile_author'] = author_to_view

        # 2. Get the user who is currently logged in (the viewer)
        viewer = self.request.user

        # 3. Determine which entries to show based on visibility
        visible_statuses = ['PUBLIC']
        is_friend = False

        if viewer.is_authenticated:
            # If you are viewing your own profile, you see everything
            if viewer == author_to_view:
                visible_statuses.extend(['FRIENDS', 'UNLISTED'])
            # Check if you are friends (mutual followers)
            elif viewer.is_friend_with(author_to_view):
                visible_statuses.append('FRIENDS')
                is_friend = True

        # 4. Fetch the entries with the correct visibility
        entries = Entry.objects.filter(
            author=author_to_view,
            visibility__in=visible_statuses,
            is_deleted=False
        ).order_by('-published')

        context['is_friend'] = is_friend
        context['currentAuthor'] = viewer

        serializer = EntrySerializer(entries, many=True, context={
                                     'request': self.request})
        entries_json = JSONRenderer().render(serializer.data).decode('utf-8')
        context['entries_json'] = entries_json
        return context


@extend_schema(
    summary="Post to an Author's Inbox",
    description=(
        """
        ### Functionality
        The Inbox is the primary mechanism for creating social interactions.
        It acts as a router. You send an object with a `type` field, and the
        server processes it accordingly. When an action is sent to an inbox,
        it is up to the inbox owner's server to process it.

        ### When to Use
        - To **follow** an author (`type: "follow"`).
        - To **like** an entry or comment (`type: "like"`).
        - To **comment** on an entry (`type: "comment"`).
        For example, when Author1 wishes to follow Author2, Author1's node
        sends a `follow` object to Author2's inbox. It is then up to Author2
        to accept or reject this follow request.

        ### Action Types
        - **`follow`**: To request to follow an author. The `actor` is the
          follower, and the `object` is the author to be followed.
        - **`like`**: To like an entry or comment.
        - **`comment`**: To comment on an entry.

        ### How to Use
        - **Actor**: The `actor` is the author performing the action.
            - For local requests, the `actor` is the authenticated user.
            - For remote/federated requests, the `actor` object must be
              provided in the request body.
        - **Recipient**: The author identified by `serial` in the URL is the
          owner of the inbox, and the recipient of the action.
            - For a `follow` request, the request is sent to the `object`'s
              inbox, so the recipient (inbox owner) MUST be the `object` of
              the follow.
        - The request body's structure depends on the `type`. See the
          examples.

        ### Important Notes
        - **Asynchronous Follows**: A successful response to a `follow`
          request only indicates it has been received. The receiving server
          does not notify the sender whether the follow was accepted or
          rejected.
        - **Permissions**: You cannot like or comment on content you don't
          have permission to see (e.g., a "Friends-Only" post from a
          non-friend).
        - **Object FQIDs**: When liking or commenting, you must provide the
          FQID of the object you are interacting with.
        """
    ),
    request=inline_serializer(
        name='InboxRequest',
        fields={
            'type': serializers.ChoiceField(
                choices=['follow', 'like', 'comment'],
                help_text="The type of action to perform."
            ),
            'summary': serializers.CharField(
                required=False,
                help_text='(For `follow` requests) A summary of the action.'
            ),
            'actor': serializers.JSONField(
                required=False,
                help_text=(
                    '(For `follow` requests) The author performing the action.'
                )
            ),
            'object': serializers.JSONField(
                required=False,
                help_text=(
                    'The object of the action. '
                    '(For `follow`: the author to be followed. '
                    'For `like`: the FQID of the entry/comment to be liked.)'
                )
            ),
            'comment': serializers.CharField(
                required=False,
                help_text=(
                    '(For `comment` requests) The content of the comment.'
                )
            ),
            'contentType': serializers.CharField(
                required=False,
                default='text/plain',
                help_text='(For `comment` requests) e.g., "text/plain".'
            ),
            'entry': serializers.CharField(
                required=False,
                help_text='(For `comment` requests) The FQID of the entry.'
            ),
        }
    ),
    examples=[
        OpenApiExample(
            "Follow Request Example",
            summary="Sending a Follow Request",
            value={
                "type": "follow",
                "summary": "Greg wants to follow Lara Croft",
                "actor": {
                    "type": "author",
                    "id": (
                        "http://127.0.0.1:8000/api/authors/"
                        "c4c5d04c-2c6f-6c8d-ac9f-5d8d6e5f5d8e"
                    ),
                    "host": "http://127.0.0.1:8000/",
                    "displayName": "Greg Johnson",
                    "github": "http://github.com/gjohnson",
                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg",
                    "web": (
                        "http://127.0.0.1:8000/authors/"
                        "c4c5d04c-2c6f-6c8d-ac9f-5d8d6e5f5d8e"
                    )
                },
                "object": {
                    "type": "author",
                    "id": (
                        "http://127.0.0.1:8000/api/authors/"
                        "a2a3d02a-0a4f-4a6b-8a7e-3b6b4d3f3b6c"
                    ),
                    "host": "http://127.0.0.1:8000/",
                    "displayName": "Lara Croft",
                    "github": "http://github.com/laracroft",
                    "profileImage": "https://i.imgur.com/k7XVwpB.jpeg",
                    "web": (
                        "http://127.0.0.1:8000/authors/"
                        "a2a3d02a-0a4f-4a6b-8a7e-3b6b4d3f3b6c"
                    )
                }
            },
            request_only=True
        ),
        OpenApiExample(
            "Like Request Example",
            summary="Liking an Entry",
            value={
                "type": "like",
                "object": (
                    "http://127.0.0.1:8000/api/authors/"
                    "a2a3d02a-0a4f-4a6b-8a7e-3b6b4d3f3b6c/entries/"
                    "d5f4e3c2-1b6a-4b8c-9c7d-8e6f5d3e2c1a"
                )
            },
            request_only=True
        ),
        OpenApiExample(
            "Comment Request Example",
            summary="Commenting on an Entry",
            value={
                "type": "comment",
                "comment": "This is a great post!",
                "contentType": "text/plain",
                "entry": (
                    "http://127.0.0.1:8000/api/authors/"
                    "a2a3d02a-0a4f-4a6b-8a7e-3b6b4d3f3b6c/entries/"
                    "d5f4e3c2-1b6a-4b8c-9c7d-8e6f5d3e2c1a"
                )
            },
            request_only=True
        ),
        OpenApiExample(
            "Successful Response",
            summary="Example Success Response",
            value={"detail": "Action processed successfully."},
            response_only=True,
            status_codes=[201]
        )
    ],
    responses={
        201: OpenApiResponse(
            description="Action processed and object created successfully."
        ),
        400: OpenApiResponse(
            description=(
                "Bad Request. The request body may be invalid or the action "
                "cannot be performed. This can be due to: an unsupported "
                "object `type`, malformed data, a `follow` request where the "
                "`actor` does not match the authenticated user or the "
                "`object` does not match the inbox owner, an attempt to "
                "follow oneself, or a duplicate follow request."
            )
        ),
        401: OpenApiResponse(
            description="Unauthorized. Authentication is required to post to "
                        "an inbox."
        ),
        403: OpenApiResponse(
            description=(
                "Permission Denied. The user does not have permission to "
                "perform the action. This can happen when the `actor` in a "
                "`follow` request does not match the authenticated user, or "
                "when liking/commenting on a friends-only post you cannot see."
            )
        ),
        404: OpenApiResponse(
            description=(
                "Not Found. A resource was not found, such as the author's "
                "inbox or the entry/comment being acted upon."
            )
        )
    },
    tags=['Inbox']
)
class InboxView(APIView):
    """
    The inbox is where all incoming activities are sent from other nodes.
    It authenticates requests and processes the incoming data based on its
    type.
    """
    authentication_classes = [RemoteNodeAuthentication, SessionAuthentication]
    permission_classes = [CanPostToInbox]

    def post(self, request, author_serial):
        """
        Handles POST requests to an author's inbox. It routes the request
        to the appropriate handler based on the object's 'type'.
        """
        inbox_owner = get_object_or_404(Author, serial=author_serial)

        # Check if this is a request for a remote author (proxy)
        # If so, forward it to the remote node instead of processing locally
        if self._is_remote_author(inbox_owner, request):
            return self._forward_to_remote_inbox(inbox_owner, request.data)

        data = request.data
        obj_type = data.get('type', '').lower()

        handler_map = {
            'follow': self._handle_follow_request,
            'like': self._handle_like,
            'comment': self._handle_comment,
            'entry': self._handle_entry,
        }

        handler = handler_map.get(obj_type)
        if not handler:
            return Response(
                {"detail": f"Object type '{obj_type}' not supported."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return handler(request, inbox_owner)

    def _forward_activity_to_owner(self, activity_data, target_object):
        """
        Forwards an activity (like, comment) to the inbox of the author who
        owns the target object, if they are remote.

        Args:
            activity_data (dict): The full JSON
            payload of the activity to send.
            target_object (Entry or Comment): The object being acted upon.
        """
        # Determine the owner of the content
        if isinstance(target_object, Entry):
            owner = target_object.author
        elif isinstance(target_object, Comment):
            # Activities on comments are sent to the original entry's author
            owner = target_object.entry.author
        else:
            return  # Not a target type we can forward for

        # If the owner is local, no need to forward
        if not self._is_remote_author(owner, self.request):
            return

        # Find the remote node configuration to get auth credentials
        remote_node = RemoteNode.objects.filter(
            host__startswith=owner.host, is_active=True).first()
        if not remote_node:
            return

        # The inbox URL is the owner's API URL plus "/inbox/"
        inbox_url = f"{owner.get_api_url(self.request)}inbox/"
        auth = HTTPBasicAuth(
            remote_node.outgoing_username,
            remote_node.outgoing_password)

        try:
            requests.post(
                inbox_url,
                json=activity_data,
                auth=auth,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'},
                timeout=10).raise_for_status()
        except requests.exceptions.RequestException:
            # Silently fail if forwarding does not succeed
            pass

    def _handle_entry(self, request, inbox_owner):
        """
        Processes an incoming Entry object sent to the inbox, respecting its
        original visibility.
        """
        entry_data = request.data

        author_data = entry_data.get('author')
        if not author_data:
            return Response({"detail": "must include an 'author' object."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            entry_author = get_or_create_proxy_author(author_data, request)
        except ValueError as e:
            return Response({"detail": str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        # Security Check: Ensure the inbox owner actually follows the entry's
        # author
        is_follower = Follow.objects.filter(
            follower=inbox_owner,
            following=entry_author,
            status=Follow.Status.ACCEPTED
        ).exists()
        if not is_follower:
            return Response(
                {
                    "detail": "Inbox owner doesn't follow the entry author."},
                status=status.HTTP_403_FORBIDDEN)

        # Get or create entry: Update existing entries, create new ones
        entry_url = entry_data.get('id') or entry_data.get('url')
        if not entry_url:
            return Response(
                {
                    "detail": "Entry must include a unique 'id' or 'url'."},
                status=status.HTTP_400_BAD_REQUEST)

        existing_entry = Entry.objects.filter(url=entry_url).first()

        # Validate visibility
        incoming_visibility = entry_data.get('visibility', 'PUBLIC').upper()
        valid_visibilities = [choice[0] for choice in VISIBILITY_CHOICES]
        if incoming_visibility not in valid_visibilities:
            return Response(
                {"detail": f"Invalid visibility: '{incoming_visibility}'"},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            if existing_entry:
                # Update existing entry
                existing_entry.title = entry_data.get(
                    'title', existing_entry.title)
                existing_entry.description = entry_data.get(
                    'description', existing_entry.description)
                existing_entry.content_type = entry_data.get(
                    'contentType', existing_entry.content_type)
                existing_entry.content = entry_data.get(
                    'content', existing_entry.content)
                existing_entry.visibility = incoming_visibility
                if incoming_visibility == 'DELETED':
                    existing_entry.is_deleted = True
                if entry_data.get('published'):
                    existing_entry.published = entry_data.get('published')
                existing_entry.save()
                return Response({"detail": "Entry updated successfully."},
                                status=status.HTTP_200_OK)
            else:
                # Create new entry
                Entry.objects.create(
                    author=entry_author,
                    url=entry_url,
                    title=entry_data.get('title', ''),
                    description=entry_data.get('description', ''),
                    content_type=entry_data.get('contentType', 'text/plain'),
                    content=entry_data.get('content', ''),
                    visibility=incoming_visibility,
                    published=entry_data.get('published'),
                    is_deleted=incoming_visibility == 'DELETED',
                )
                return Response({"detail": "Entry received and saved."},
                                status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": f"Failed to save entry locally: {e}"},
                            status=status.HTTP_400_BAD_REQUEST)

    def _is_remote_author(self, author, request):
        """
        Check if an author is a remote proxy author by comparing their host
        to the current request's host.
        """
        if not author.host:
            return False

        current_host = f"{request.scheme}://{request.get_host()}/"
        author_host = author.host.rstrip('/') + '/'

        # Handle cases where author.host includes '/api/' suffix
        current_base = current_host.rstrip('/')
        author_base = author_host.rstrip('/').replace('/api', '')

        # If the base hosts match, this is a local author
        if author_base == current_base:
            return False

        # If hosts differ, this is a remote author
        return author_host != current_host

    def _forward_to_remote_inbox(self, remote_author, data):
        """
        Forward the inbox request to the remote author's actual inbox
        using the NodeService.
        """
        node_service = NodeService()

        try:
            # Send to the remote author's inbox
            response = node_service.send_to_inbox(remote_author.url, data)

            if response:
                # Successfully forwarded - handle local side effects
                self._handle_successful_remote_forward(remote_author, data)

                # Forward the remote response back to the client
                try:
                    response_data = response.json()
                    return Response(response_data, status=response.status_code)
                except (ValueError, requests.exceptions.JSONDecodeError):
                    # If response isn't JSON, just return success
                    return Response(
                        {"detail": "Request forwarded successfully."},
                        status=response.status_code
                    )
            else:
                # NodeService returned None (likely no remote node config)
                return Response(
                    {
                        "detail": (
                            "Unable to forward to remote node - "
                            "no configuration found."
                        )
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

        except Exception as e:
            # Handle any network or other errors
            return Response(
                {"detail": f"Failed to forward to remote node: {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

    def _handle_successful_remote_forward(self, remote_author, data):
        """
        Handle local side effects when a request is successfully
        forwarded to a remote node.
        When sending a follow request to a remote author,
        the sending node should assume the follow is established immediately.
        """
        obj_type = data.get('type', '').lower()

        if obj_type == 'follow':
            try:
                # Get the local actor who sent the request
                if hasattr(self.request.user, 'serial'):
                    # Local authenticated user
                    local_actor = self.request.user
                else:
                    # This shouldn't happen for follow requests
                    return

                # "A's node can assume that A is following B"
                # Create or update the local follow relationship
                follow, created = Follow.objects.get_or_create(
                    follower=local_actor,
                    following=remote_author,
                    defaults={'status': Follow.Status.ACCEPTED}
                )

                if not created and follow.status != Follow.Status.ACCEPTED:
                    # Update existing relationship to accepted
                    follow.status = Follow.Status.ACCEPTED
                    follow.save()

            except Exception:
                # Don't fail the whole request if local relationship creation
                # fails
                pass

    def _user_can_view_entry(self, user, entry):
        """Check if a user has permission to view an entry."""
        if entry.visibility in ['PUBLIC', 'UNLISTED']:
            return True

        if not user.is_authenticated:
            return False

        if entry.author == user:
            return True

        if entry.visibility == 'FRIENDS':
            return user.is_friend_with(entry.author)

        return False

    def _handle_follow_request(self, request, inbox_owner):
        """
        Processes an incoming Follow request object.
        """
        data = request.data

        # The 'object' of the follow request must be the inbox owner.
        object_data = data.get('object', {})
        object_id = object_data.get('id')

        # Check if the object ID matches either the stored FQID or the API URL
        # Normalize URLs by removing trailing slashes for comparison
        def normalize_url(url):
            return url.rstrip('/') if url else url

        normalized_object_id = normalize_url(object_id)
        normalized_api_url = normalize_url(inbox_owner.get_api_url(request))
        normalized_inbox_url = normalize_url(
            inbox_owner.url) if inbox_owner.url else None

        if (
            normalized_object_id != normalized_api_url and
            (not normalized_inbox_url or
             normalized_object_id != normalized_inbox_url)
        ):
            return Response(
                {
                    "detail": (
                        "Follow request object ID does not match "
                        "inbox owner's URL."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # The 'actor' is the author who wants to follow.
        actor_data = data.get('actor', {})

        # Handle different types of request users
        if isinstance(request.user, RemoteNode):
            # Request from another node - create proxy author from actor_data
            try:
                actor = get_or_create_proxy_author(actor_data, request)
            except ValueError as e:
                return Response({"detail": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)
        elif (
            hasattr(request.user, 'is_authenticated')
            and request.user.is_authenticated
        ):
            # Local authenticated user
            actor = request.user
            if actor_data and actor_data.get(
                    'id') != actor.get_api_url(request):
                return Response(
                    {
                        "detail": (
                            "Actor in payload does not match "
                            "authenticated user."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            # Unauthenticated request - need actor_data
            try:
                actor = get_or_create_proxy_author(actor_data, request)
            except ValueError as e:
                return Response({"detail": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)

        # Handle existing follow requests
        try:
            existing_follow = Follow.objects.get(
                follower=actor, following=inbox_owner)
            # If request exists and is pending, return existing request
            # (idempotent)
            if existing_follow.status == Follow.Status.PENDING:
                serializer = FollowSerializer(
                    existing_follow, context={'request': request})
                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK
                )
            # If already accepted, return success (idempotent)
            elif existing_follow.status == Follow.Status.ACCEPTED:
                serializer = FollowSerializer(
                    existing_follow, context={'request': request})
                return Response(
                    serializer.data,
                    status=status.HTTP_200_OK
                )
            # If it was rejected, we allow a new request by updating the
            # status.
            else:
                existing_follow.status = Follow.Status.PENDING
                existing_follow.save()
                serializer = FollowSerializer(
                    existing_follow, context={
                        'request': request})
                return Response(
                    serializer.data,
                    status=status.HTTP_201_CREATED)
        except Follow.DoesNotExist:
            pass  # No existing request, so we can proceed to create one.

        # Create the follow request.
        try:
            follow = Follow.objects.create(
                follower=actor,
                following=inbox_owner
            )
        except ValidationError as e:
            return Response(
                {"detail": e.messages[0]}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FollowSerializer(follow, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # In authors/views.py inside the InboxView class

    def _handle_like(self, request, inbox_owner):
        """
        Processes an incoming Like object by saving it locally.
        The fan-out is handled by a signal.
        """
        data = request.data
        actor = request.user

        if isinstance(actor, RemoteNode):
            try:
                author_data = data.get('author') or data.get('actor') or {}
                if not author_data:
                    return Response(
                        {
                            "detail": ("Like from remote node must include an "
                                       "'author' object.")},
                        status=status.HTTP_400_BAD_REQUEST)

                actor = get_or_create_proxy_author(author_data, request)
            except ValueError as e:
                return Response({"detail": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)

        object_fqid = data.get('object')
        if not object_fqid:
            return Response({"detail": "Like must include an 'object' FQID."},
                            status=status.HTTP_400_BAD_REQUEST)

        liked_object = get_object_from_fqid(object_fqid)
        if not liked_object:
            return Response({"detail": "Liked object not found."},
                            status=status.HTTP_404_NOT_FOUND)

        entry_to_check = liked_object if isinstance(
            liked_object, Entry) else liked_object.entry

        if not self._user_can_view_entry(actor, entry_to_check):
            return Response(
                {
                    "detail": "You don't have permission to like content."},
                status=status.HTTP_403_FORBIDDEN)

        content_type = ContentType.objects.get_for_model(liked_object)
        like_url = data.get('id') or data.get('url')

        if like_url:
            like, created = Like.objects.update_or_create(
                url=like_url,
                defaults={
                    'author': actor,
                    'content_type': content_type,
                    'object_id': liked_object.url,
                    'published': data.get('published', timezone.now())
                }
            )
        else:
            like, created = Like.objects.get_or_create(
                author=actor,
                content_type=content_type,
                object_id=liked_object.url,
                defaults={
                    'url':
                    f"{actor.get_api_url(request)}/liked/{uuid.uuid4()}",
                    'published': timezone.now()
                }
            )
            if not created:
                return Response({"detail": "Object already liked."},
                                status=status.HTTP_409_CONFLICT)

        serializer = LikeSerializer(like, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _handle_comment(self, request, inbox_owner):
        """
        Processes an incoming Comment by saving it locally.
        The fan-out is handled by a signal.
        """
        data = request.data
        actor = request.user

        if isinstance(actor, RemoteNode):
            try:
                author_data = data.get('author') or data.get('actor') or {}
                actor = get_or_create_proxy_author(author_data, request)
            except ValueError as e:
                return Response({"detail": str(e)},
                                status=status.HTTP_400_BAD_REQUEST)

        entry_fqid = data.get('entry')
        if not entry_fqid:
            return Response({"detail": "Comment must include entry FQID."},
                            status=status.HTTP_400_BAD_REQUEST)

        entry = get_object_from_fqid(entry_fqid)
        if not entry or not isinstance(entry, Entry):
            return Response({"detail": "Entry not found."},
                            status=status.HTTP_404_NOT_FOUND)

        if not self._user_can_view_entry(actor, entry):
            return Response(
                {
                    "detail": "don't have permission to comment on this."},
                status=status.HTTP_403_FORBIDDEN)

        comment_url = data.get('id') or data.get('url')

        if comment_url:
            if Comment.objects.filter(url=comment_url).exists():
                return Response(
                    {"detail": "Comment has already been received."},
                    status=200)

            comment = Comment.objects.create(
                url=comment_url,
                author=actor,
                entry=entry,
                comment=data.get('comment'),
                content_type=data.get('contentType', 'text/plain'),
                published=data.get('published', timezone.now())
            )
        else:
            comment = Comment.objects.create(
                author=actor,
                entry=entry,
                comment=data.get('comment'),
                content_type=data.get('contentType', 'text/plain'),
                published=timezone.now(),
                url=f"{actor.get_api_url(request)}/comments/{uuid.uuid4()}"
            )

        serializer = CommentSerializer(comment, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="List Comments by Author",
    description=(
        """
        ### When to Use
        Use this endpoint to retrieve all comments made by a specific author
        across all entries.

        ### How to Use
        - The `serial_or_fqid` in the URL identifies the author whose comments
          you want to retrieve.
        - **Pagination** is supported via `?page=<number>` and
          `?size=<number>` parameters.

        ### Visibility Rules
        This endpoint has different behavior based on who is asking:
        - **Authenticated Local User**: If you are logged in, you will see
          **all** comments made by the author, regardless of the visibility
          of the entries they were posted on.
        - **Unauthenticated or Remote User**: You will only see comments made
          on `PUBLIC` or `UNLISTED` entries. Comments on `FRIENDS` entries
          will be hidden.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=PaginatedCommentSerializer,
            description="A paginated list of comments by the author."
        )
    },
    parameters=[
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description='A page number within the paginated result set.'
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Number of results to return per page.'
        ),
    ],
    tags=['Comments & Likes (Author-Centric)']
)
class AuthorCommentedListView(generics.ListAPIView):
    """
    GET /api/authors/{AUTHOR_SERIAL}/commented/ [local, remote]
    GET /api/authors/{AUTHOR_FQID}/commented/ [local]
    - get the list of comments author has made
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]
    pagination_class = StandardPagination

    def get_queryset(self):
        """
        Return comments by the specified author, filtered by visibility rules.
        - Local authenticated: show all comments by author (any entry)
        - Remote/unauthenticated: only comments on public/unlisted entries
        """
        author_or_fqid = self.kwargs.get('serial_or_fqid')
        author = get_author_from_identifier(author_or_fqid, self.request)

        # If we got an FQID back, we can't resolve this.
        if isinstance(author, str):
            # This case might require a remote request to the user's
            # 'commented' endpoint, which is not implemented.
            # For now, return an empty set.
            return Comment.objects.none()

        # Get all comments by this author
        queryset = Comment.objects.filter(author=author).select_related(
            'entry', 'entry__author'
        ).order_by('-published')

        # Apply visibility filtering based on authentication
        if self.request.user.is_authenticated:
            # Local authenticated users can see ALL comments by the author
            # This follows the spec: [local] any entry
            return queryset
        else:
            # Unauthenticated (remote) users only see comments made
            # on public/unlisted entries
            # This follows the spec: [remote] public and unlisted entries
            return queryset.filter(
                entry__visibility__in=['PUBLIC', 'UNLISTED'],
                entry__is_deleted=False
            )

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'comments' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "comments",
                "page": self.paginator.page.number,
                "size": self.paginator.page.paginator.per_page,
                "count": paginated_data['count'],
                "src": paginated_data['results'],
            })

        # This case is for when pagination is disabled
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "comments",
            "src": serializer.data
        })


@extend_schema(
    summary="Get a Specific Comment by an Author",
    description=(
        """
        ### When to Use
        Use this endpoint to retrieve a single, specific comment by its
        serial, scoped to a particular author. This is useful if you need
        to fetch the details of a comment and you know who made it.

        ### How to Use
        - `serial_or_fqid` identifies the author of the comment.
        - `comment_serial` identifies the comment itself.
        - The same visibility rules as the list view apply. A remote user
          cannot fetch a comment made on a friends-only post, which will
          result in a `404 Not Found`.
        """
    ),
    responses={
        200: CommentSerializer,
        404: OpenApiResponse(
            description="Comment not found or access denied."
        )
    },
    tags=['Comments & Likes (Author-Centric)']
)
class AuthorCommentedDetailView(generics.RetrieveAPIView):
    """
    GET /api/authors/{AUTHOR_SERIAL}
    /commented/{COMMENT_SERIAL}/ [local, remote]
    - get specific comment by author and comment serial
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get_object(self):
        """Find specific comment by author + serial with visibility checks"""
        serial_or_fqid = self.kwargs['serial_or_fqid']
        comment_serial = self.kwargs['comment_serial']

        author = get_author_from_identifier(serial_or_fqid)

        # Get the specific comment by this author
        comment = get_object_or_404(
            Comment.objects.select_related('entry', 'entry__author'),
            author=author,
            serial=comment_serial
        )

        # Check visibility permissions for the parent entry
        entry = comment.entry

        if self.request.user.is_authenticated:
            # Local authenticated users can see ANY comment by the author
            return comment
        else:
            # Unauthenticated (remote) users only see comments on
            # public/unlisted entries
            if (entry.visibility in ['PUBLIC', 'UNLISTED'] and
                    not entry.is_deleted):
                return comment
            else:
                raise Http404("Comment not found or access denied")


@extend_schema(
    summary="Get Comment by FQID",
    description=(
        "Retrieve a specific comment by its Fully-Qualified ID (FQID). "
        "This provides a direct, global way to access a comment."
    ),
    responses={
        200: CommentSerializer,
        404: OpenApiResponse(
            description="Comment not found or FQID is malformed."
        )
    },
    tags=['Comments & Likes (Object-Centric)']
)
class CommentByFQIDView(generics.RetrieveAPIView):
    """
    GET /api/commented/{COMMENT_FQID}/ [local]
    - get comment by FQID
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get_object(self):
        """Parse comment FQID and retrieve comment with permission checks"""
        comment_fqid = self.kwargs['comment_fqid']

        # Parse the FQID to get the comment
        comment = self._parse_comment_fqid(comment_fqid)

        # Check visibility permissions for the parent entry
        entry = comment.entry

        if self.request.user.is_authenticated:
            # Local authenticated users can see ANY comment
            return comment
        else:
            # Unauthenticated (remote) users only see comments on
            # public/unlisted entries
            if (entry.visibility in ['PUBLIC', 'UNLISTED'] and
                    not entry.is_deleted):
                return comment
            else:
                raise Http404("Comment not found or access denied")

    def _parse_comment_fqid(self, comment_fqid):
        """
        Parse a comment FQID and return the comment object.

        Expected FQID format:
        http://host/api/authors/{author_serial}/commented/{comment_serial}
        """
        try:
            decoded_fqid = urllib.parse.unquote(comment_fqid)

            # Parse the URL path
            parsed_url = urllib.parse.urlparse(decoded_fqid)
            path_parts = parsed_url.path.strip('/').split('/')

            # Expected path:
            # api/authors/{author_serial}/commented/{comment_serial}
            if len(path_parts) < 4 or path_parts[-2] != 'commented':
                raise ValueError("Invalid comment FQID path structure")

            comment_serial = path_parts[-1]
            # authors/{author_serial}/commented/{comment_serial}
            author_serial = path_parts[-3]

            # Find the comment by serial and author serial
            return get_object_or_404(
                Comment.objects.select_related('entry', 'entry__author'),
                serial=comment_serial,
                author__serial=author_serial
            )
        except (ValueError, IndexError, AttributeError):
            raise Http404("Comment not found or FQID is malformed")


@extend_schema(
    summary="List Likes by Author",
    description=(
        """
        ### When to Use
        Use this endpoint to get a list of all entries and comments that a
        specific author has liked.

        ### How to Use
        - `serial_or_fqid` identifies the author whose liked items you want
          to see.
        - **Pagination** is supported via `?page=<number>` and
          `?size=<number>` parameters.
        - The response includes a list of `like` objects. Each object
          contains the `author` who made the like and an `object` field
          with the FQID of the item that was liked (which could be an
          entry or a comment).
        """
    ),
    responses={
        200: OpenApiResponse(
            response=PaginatedLikeSerializer,
            description="A paginated list of likes made by the author."
        )
    },
    parameters=[
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description='A page number within the paginated result set.'
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description='Number of results to return per page.'
        ),
    ],
    tags=['Comments & Likes (Author-Centric)']
)
class AuthorLikedListView(generics.ListAPIView):
    """
    GET /api/authors/{AUTHOR_SERIAL}/liked/ [local, remote]
    Lists items an author has liked.
    - For unauthenticated users, this only shows likes on public content.
    - For authenticated users, it shows all likes.
    """
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]
    pagination_class = StandardPagination

    def get_queryset(self):
        """
        Return likes by the specified author, filtered by visibility.
        """
        author_or_fqid = self.kwargs['serial_or_fqid']
        author = get_author_from_identifier(author_or_fqid, self.request)

        # If we got an FQID back, we can't resolve this.
        if isinstance(author, str):
            # This would require proxying, which is not supported for this
            # endpoint. Return an empty set.
            return Like.objects.none()

        queryset = Like.objects.filter(author=author).order_by('-published')

        # For unauthenticated users, only show likes on public content.
        if not self.request.user.is_authenticated:
            queryset = queryset.filter(
                Q(entry__visibility='PUBLIC') |
                Q(comment__entry__visibility='PUBLIC')
            )

        return queryset

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'likes' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "likes",
                "page": self.paginator.page.number,
                "size": self.paginator.page.paginator.per_page,
                "count": paginated_data['count'],
                "src": paginated_data['results'],
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "likes",
            "src": serializer.data
        })


@extend_schema(
    summary="Get a Specific Like by an Author",
    description=(
        """
        ### When to Use
        Use this to retrieve a single `like` object made by a specific
        author.

        ### How to Use
        - `serial_or_fqid` identifies the author of the like.
        - `like_serial` identifies the like object itself.
        - Visibility rules apply: a remote user cannot fetch a `like` if
          it was made on private content. This will result in a
          `404 Not Found`.
        """
    ),
    responses={
        200: LikeSerializer,
        404: OpenApiResponse(
            description="Like not found or access denied."
        )
    },
    tags=['Comments & Likes (Author-Centric)']
)
class AuthorLikedDetailView(generics.RetrieveAPIView):
    """
    GET /api/authors/{AUTHOR_SERIAL}/liked/{LIKE_SERIAL}/ [local, remote]
    - get specific like by author and like serial
    """
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get_object(self):
        """Find specific like by author + serial with visibility checks"""
        author = get_author_from_identifier(self.kwargs['serial_or_fqid'])
        like_serial = self.kwargs['like_serial']

        like = get_object_or_404(
            Like.objects.select_related('author').prefetch_related(
                'content_object'),
            author=author,
            serial=like_serial)

        # Check visibility on the liked object
        content_object = like.content_object
        if isinstance(content_object, Entry):
            entry_to_check = content_object
        elif isinstance(content_object, Comment):
            entry_to_check = content_object.entry
        else:
            raise Http404("Liked object is not an Entry or Comment.")

        if self.request.user.is_authenticated:
            return like  # Authenticated local users can see any liked item
        else:
            # Unauthenticated users can only see likes on public/unlisted
            # entries
            if entry_to_check.visibility in [
                    'PUBLIC', 'UNLISTED'] and not entry_to_check.is_deleted:
                return like
            else:
                raise Http404("Like not found or access denied")


@extend_schema(
    summary="Get Like by FQID",
    description=(
        "Retrieve a specific like object by its Fully-Qualified ID (FQID). "
        "This provides a direct, global way to access a like."
    ),
    responses={
        200: LikeSerializer,
        404: OpenApiResponse(
            description="Like not found or FQID is malformed."
        )
    },
    tags=['Comments & Likes (Object-Centric)']
)
class LikeByFQIDView(generics.RetrieveAPIView):
    """
    GET /api/liked/{LIKE_FQID}/ [local]
    - get like by FQID
    """
    serializer_class = LikeSerializer
    permission_classes = [IsAuthenticatedOrReadOnlyForPublic]

    def get_object(self):
        """Parse like FQID and retrieve like with permission checks"""
        like = self._parse_like_fqid(self.kwargs['like_fqid'])

        # Check visibility on the liked object
        content_object = like.content_object
        if isinstance(content_object, Entry):
            entry_to_check = content_object
        elif isinstance(content_object, Comment):
            entry_to_check = content_object.entry
        else:
            raise Http404("Liked object is not an Entry or Comment.")

        if self.request.user.is_authenticated:
            return like
        else:
            if entry_to_check.visibility in [
                    'PUBLIC', 'UNLISTED'] and not entry_to_check.is_deleted:
                return like
            else:
                raise Http404("Like not found or access denied")

    def _parse_like_fqid(self, like_fqid):
        """
        Parse a like FQID and return the like object.
        Expected FQID format:
        http://host/api/authors/{author_serial}/liked/{like_serial}
        """
        try:
            decoded_fqid = urllib.parse.unquote(like_fqid)
            parsed_url = urllib.parse.urlparse(decoded_fqid)
            path_parts = parsed_url.path.strip('/').split('/')

            if len(path_parts) < 4 or path_parts[-2] != 'liked':
                raise ValueError("Invalid like FQID path structure")

            like_serial = path_parts[-1]
            author_serial = path_parts[-3]

            return get_object_or_404(
                Like.objects.select_related('author').prefetch_related(
                    'content_object'),
                serial=like_serial,
                author__serial=author_serial
            )
        except (ValueError, IndexError, AttributeError):
            raise Http404("Like not found or FQID is malformed")


@extend_schema(
    summary="List Pending Follow Requests",
    description=(
        """
        ### When to Use
        Use this endpoint to retrieve a list of pending follow requests for
        the **currently authenticated user**. This is how a user can see who
        wants to follow them so they can approve or deny requests.

        ### How to Use
        - This endpoint requires authentication.
        - The `serial_or_fqid` in the URL **must** belong to the
          authenticated user. You cannot view the pending requests for
          another user.
        - A successful request returns a list of `follow` objects, each
          representing a pending request.
        """
    ),
    responses={
        200: OpenApiResponse(
            response=FollowSerializer(many=True),
            description=(
                "A list of pending follow requests was successfully retrieved."
            ),
            examples=[
                OpenApiExample(
                    "Pending Requests Example",
                    value=[
                        {
                            "type": "follow",
                            "summary": "Charlie wants to follow Lara Croft",
                            "actor": {
                                "type": "author",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "d4d5e05d-3d7f-7d9e-bd0f-6e9e7f6f6e9f"
                                ),
                                "displayName": "Charlie"
                            },
                            "object": {
                                "type": "author",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "a2a3d02a-0a4f-4a6b-8a7e-3b6b4d3f3b6c"
                                ),
                                "displayName": "Lara Croft"
                            }
                        }
                    ]
                )
            ]
        ),
        403: OpenApiResponse(
            description=(
                "Permission denied. You can only view your own follow "
                "requests."
            )
        ),
    },
    tags=['Followers']
)
class PendingFollowRequestsView(APIView):  # Changed from generics.ListAPIView
    """
    GET /api/authors/{serial}/follow-requests/ [local]
    - get list of pending follow requests for this author
    """
    permission_classes = [IsAuthenticated]  # Ensures user is logged in

    def get(self, request, *args, **kwargs):
        """
        Return pending follow requests for the currently authenticated user.
        """
        try:
            author_to_check = get_author_from_identifier(
                self.kwargs['serial_or_fqid'], request)
        except Exception:
            return Response(
                {"detail": "Author not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Explicitly check if the logged-in user is the one being requested
        if request.user != author_to_check:
            return Response(
                {"detail": "You can only view your own follow requests."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get the queryset from the model method
        pending_requests = author_to_check.get_pending_follow_requests()

        # Serialize the data
        serializer = FollowSerializer(
            pending_requests, many=True, context={'request': request}
        )

        # Return the response
        return Response(serializer.data, status=status.HTTP_200_OK)


class FollowersPageView(TemplateView):
    template_name = 'authors/followers_list.html'


class FollowingPageView(TemplateView):
    template_name = 'authors/following_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_user'] = self.request.user
        return context


class FriendsPageView(TemplateView):
    template_name = 'authors/friends_list.html'


class AuthorProfilePageEditView(TemplateView):
    template_name = 'authors/profile_edit.html'


@receiver(post_save, sender=Entry)
def fan_out_entry_to_followers(sender, instance, created, **kwargs):
    """
    After an Entry is created or updated, send it to the inboxes of all the
    author's remote followers based on visibility rules.
    """

    author = instance.author

    if instance.visibility not in ['PUBLIC', 'UNLISTED', 'FRIENDS', 'DELETED']:
        return

    if instance.visibility in ['PUBLIC', 'UNLISTED']:
        followers_qs = Follow.objects.filter(
            following=author, status=Follow.Status.ACCEPTED)
    elif instance.visibility == 'FRIENDS':
        friend_serials = author.get_friends().values_list('serial', flat=True)
        followers_qs = Follow.objects.filter(
            following=author,
            follower__serial__in=friend_serials,
            status=Follow.Status.ACCEPTED
        )
    elif instance.visibility == 'DELETED':
        # For deleted entries, send to all followers (previously notified)
        followers_qs = Follow.objects.filter(
            following=author, status=Follow.Status.ACCEPTED)

    followers = followers_qs.select_related('follower')

    if not followers.exists():
        return

    author_data = {
        "type": "author",
        "id": author.get_api_url(),
        "host": author.host.rstrip("api/").rstrip("/") + "/",
        "displayName": author.display_name,
        "github": author.github,
        "profileImage": author.profile_image,
        "web": author.get_web_url()
    }
    pub = instance.published.isoformat() if instance.published else None
    entry_data = {
        "type": "entry",
        "title": instance.title,
        "id": instance.url,
        "url": instance.url,
        "web": instance.get_web_url(),
        "description": instance.description,
        "contentType": instance.content_type,
        "content": instance.content,
        "author": author_data,
        "visibility": instance.visibility,
        "published": pub,
        "comments": f"{instance.url}/comments"
    }

    node_service = NodeService()
    for follow_obj in followers:
        follower = follow_obj.follower

        if follower.host == author.host:
            continue

        try:
            response = node_service.send_to_inbox(
                follower.get_api_url(), entry_data)
            if response:
                response.raise_for_status()
        except requests.exceptions.RequestException:
            # Silently fail if fan-out to a specific node fails
            pass


@receiver(post_save, sender=Like)
def fan_out_like(sender, instance, created, **kwargs):
    """
    After a new Like is created, send it to everyone who can see the
    liked entry.
    This follows the same distribution pattern as entries:
    - For PUBLIC/UNLISTED entries: sent to all followers of the entry author
    - For FRIENDS entries: sent to all friends of the entry author
    """
    if not created:
        return

    like_author = instance.author
    liked_object = instance.content_object

    # Determine the entry being liked
    if isinstance(liked_object, Entry):
        entry = liked_object
    elif isinstance(liked_object, Comment):
        entry = liked_object.entry
    else:
        return

    entry_author = entry.author

    # Only distribute likes for entries that are distributed to other nodes
    if entry.visibility not in ['PUBLIC', 'UNLISTED', 'FRIENDS']:
        return

    # Determine who should receive the like based on entry visibility
    # This matches the entry distribution logic
    if entry.visibility in ['PUBLIC', 'UNLISTED']:
        # For public/unlisted entries: send to all followers of the entry
        # author
        followers_qs = Follow.objects.filter(
            following=entry_author, status=Follow.Status.ACCEPTED)
    elif entry.visibility == 'FRIENDS':
        # For friends-only entries: send to all friends of the entry author
        friend_serials = entry_author.get_friends().values_list(
            'serial', flat=True)
        followers_qs = Follow.objects.filter(
            following=entry_author,
            follower__serial__in=friend_serials,
            status=Follow.Status.ACCEPTED
        )

    followers = followers_qs.select_related('follower')

    if not followers.exists():
        return

    like_author_data = {
        "type": "author",
        "id": like_author.get_api_url(),
        "host": like_author.host,
        "displayName": like_author.display_name,
        "github": like_author.github,
        "profileImage": like_author.profile_image,
        "web": like_author.get_web_url()}
    like_payload = {
        "type": "like",
        "author": like_author_data,
        "object": liked_object.url,
        "id": instance.url,
        "url": instance.url,
        "published": instance.published.isoformat()}

    node_service = NodeService()
    # First, send to the entry author (if on a different node)
    if entry_author.host != like_author.host:
        try:
            response = node_service.send_to_inbox(
                entry_author.get_api_url(), like_payload)
            if response:
                response.raise_for_status()
        except requests.exceptions.RequestException:
            logging.warning(
                f"Failed to send like to {entry_author.get_api_url()}")

    # Then send to all remote followers/friends who can see the entry
    for follow_obj in followers:
        follower = follow_obj.follower

        # Skip local followers (same host as entry author)
        if follower.host == entry_author.host:
            continue

        # Skip if this is the same as entry author (already sent above)
        if follower.serial == entry_author.serial:
            continue

        try:
            response = node_service.send_to_inbox(
                follower.get_api_url(), like_payload)
            if response:
                response.raise_for_status()
        except requests.exceptions.RequestException:
            logging.warning(f"Failed to send like to {follower.get_api_url()}")


@receiver(post_save, sender=Comment)
def fan_out_comment(sender, instance, created, **kwargs):
    """
    After a new Comment is created, send it to the original content's author
    and all followers of the user who created the comment.
    """
    if not created:
        return

    comment_author = instance.author
    original_author = instance.entry.author

    recipients = {original_author}
    recipients.update(comment_author.get_followers())

    comment_author_data = {
        "type": "author",
        "id": comment_author.get_api_url(),
        "host": comment_author.host,
        "displayName": comment_author.display_name,
        "github": comment_author.github,
        "profileImage": comment_author.profile_image,
        "web": comment_author.get_web_url()}
    comment_payload = {
        "type": "comment",
        "author": comment_author_data,
        "comment": instance.comment,
        "contentType": instance.content_type,
        "published": instance.published.isoformat(),
        "id": instance.url,
        "url": instance.url,
        "entry": instance.entry.url}

    node_service = NodeService()
    for recipient in recipients:
        if recipient.serial == comment_author.serial:
            continue

        if recipient.host == comment_author.host:
            continue

        try:
            response = node_service.send_to_inbox(
                recipient.get_api_url(), comment_payload)
            if response:
                response.raise_for_status()
        except requests.exceptions.RequestException:
            logging.warning(
                f"Failed to send comment to {recipient.get_api_url()}")


@receiver(post_save, sender=Author)
def fan_out_author_updates_to_remote_nodes(
        sender, instance, created, **kwargs):
    """
    After an Author is updated (not created), notify remote nodes where
    followers are located by making PUT requests to the author detail API.
    This ensures remote nodes have up-to-date author information.
    """
    if created:
        return  # Only handle updates, not creation

    # Only fanout if this is a local author (not a remote proxy)
    current_host = instance.host.rstrip('/') + '/'
    if not instance.host or '/api/' in current_host:
        return

    # Get all followers from remote nodes
    followers = instance.get_followers().exclude(host=current_host)

    if not followers.exists():
        return

    # Prepare the updated author data
    author_data = {
        "type": "author",
        "id": instance.get_api_url(),
        "host": instance.host,
        "displayName": instance.display_name,
        "github": instance.github,
        "profileImage": instance.profile_image,
        "web": instance.get_web_url()
    }

    # Send the updated author data to each remote follower's inbox
    node_service = NodeService()
    for follower in followers:
        try:
            response = node_service.send_to_inbox(
                follower.get_api_url(), author_data)
            if response:
                response.raise_for_status()
        except requests.exceptions.RequestException:
            logging.warning(
                f"Failed to notify follower {follower.get_api_url()} "
                f"about author update for {instance.get_api_url()}"
            )
