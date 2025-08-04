from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404
from rest_framework import generics
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import (
    extend_schema, OpenApiResponse, OpenApiExample, inline_serializer,
    OpenApiParameter
)
from .models import Author, Entry, Comment, Like
from .serializers import (
    EntrySerializer, CommentSerializer, LikeSerializer, EntryListSerializer,
    CommentListResponseSerializer, LikeListResponseSerializer
)
from .permissions import (
    EntryPermission,
    CanAccessContentPermission,
    FQIDBasedPermission,
)
from .utils import parse_entry_fqid, get_response_image_content_type
import base64
from .github_service import process_github_events
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from authors.views import StandardPagination
import uuid


@extend_schema(
    summary="Retrieve the User's Stream",
    description=(
        """
### Functionality
This endpoint retrieves a personalized stream of entries for the
authenticated user.

### When to Use
Use this endpoint to load the main feed or timeline for a logged-in
user. It aggregates all entries the user is allowed to see into a
single, chronologically sorted list.

### How to Use
- Send a GET request to this endpoint while authenticated.
- Pagination is supported using `?page=<number>` and `?size=<number>`.

### Visibility Rules
The stream combines multiple sources based on the user's relationships:
- All `PUBLIC` entries from every author known to the node.
- `FRIENDS` and `UNLISTED` entries from authors the user is friends with
  (i.e., mutual followers).
- `UNLISTED` entries from authors the user follows (but is not friends
  with).
"""
    ),
    responses={
        200: OpenApiResponse(
            response=EntryListSerializer,
            description="A paginated list of stream entries was retrieved.",
            examples=[
                OpenApiExample(
                    "Successful Stream Response",
                    value={
                        "type": "entries",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "src": [
                            {
                                "type": "entry",
                                "title": "Hello",
                                "id": (
                                    "http://127.0.0.1:8000/api/authors/"
                                    "1ca872dc-7664-4622-b21c-d3c25e5cd3cc/"
                                    "entries/"
                                    "87dd3f77-5a3d-4929-a523-b692cb333fa9"
                                ),
                                "web": (
                                    "http://127.0.0.1:8000/authors/"
                                    "1ca872dc-7664-4622-b21c-d3c25e5cd3cc/"
                                    "entries/"
                                    "87dd3f77-5a3d-4929-a523-b692cb333fa9"
                                ),
                                "description": "",
                                "contentType": "text/plain",
                                "content": "I am A",
                                "author": {
                                    "type": "author",
                                    "id": (
                                        "http://127.0.0.1:8000/api/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                    ),
                                    "host": "http://127.0.0.1:8000/",
                                    "displayName": "a",
                                    "github": "",
                                    "profileImage": "",
                                    "web": (
                                        "http://127.0.0.1:8000/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                    ),
                                    "followers_count": 0,
                                    "following_count": 1,
                                    "friends_count": 0
                                },
                                "comments": {
                                    "type": "comments",
                                    "id": (
                                        "http://127.0.0.1:8000/api/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-b692cb333fa9/"
                                        "comments"
                                    ),
                                    "web": (
                                        "http://127.0.0.1:8000/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-b692cb333fa9/"
                                        "comments"
                                    ),
                                    "page_number": 1,
                                    "size": 5,
                                    "count": 0,
                                    "src": []
                                },
                                "likes": {
                                    "type": "likes",
                                    "id": (
                                        "http://127.0.0.1:8000/api/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-"
                                        "b692cb333fa9/"
                                        "likes"
                                    ),
                                    "web": (
                                        "http://127.0.0.1:8000/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-"
                                        "b692cb333fa9/"
                                        "likes"
                                    ),
                                    "page_number": 1,
                                    "size": 5,
                                    "count": 0,
                                    "src": []
                                },
                                "published": (
                                    "2025-06-22T23:35:17.231226-06:00"
                                ),
                                "visibility": "PUBLIC"
                            }
                        ]
                    }
                )
            ]
        ),
        401: OpenApiResponse(
            description="Authentication credentials were not provided."
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
    tags=['Stream']
)
class StreamView(generics.ListAPIView):
    """
    GET: List all entries for the current user's stream.
    """
    serializer_class = EntrySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self):
        """
        This view should return a list of all entries that should appear in
        the user's stream. This includes:
        - All public entries from all authors.
        - All friends-only and unlisted entries from friends.
        - All unlisted entries from followed authors.
        """
        user = self.request.user

        # Get authors the user is following and is friends with
        following_authors = Author.objects.filter(
            follower_relationships__follower=user,
            follower_relationships__status='ACCEPTED'
        )
        friends = Author.objects.filter(
            pk__in=following_authors.values('pk'),
            following_relationships__following=user,
            following_relationships__status='ACCEPTED'
        )

        # 1. All of the user's own entries
        own_entries_q = Q(author=user)

        # 2. All public entries
        public_entries_q = Q(visibility='PUBLIC')

        # 3. All friends-only entries from friends
        friends_entries_q = Q(
            author__in=friends,
            visibility='FRIENDS'
        )

        # 4. All unlisted entries from followed authors
        unlisted_entries_q = Q(
            author__in=following_authors,
            visibility='UNLISTED'
        )

        # Combine the querysets
        queryset = Entry.objects.filter(
            own_entries_q |
            public_entries_q |
            friends_entries_q |
            unlisted_entries_q,
            is_deleted=False
        ).distinct().order_by('-published')

        return queryset

    def list(self, request, *args, **kwargs):
        process_github_events(request.user)
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "entries",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "src": paginated_data['results'],
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "entries",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "src": serializer.data
        })


@extend_schema(
    summary="List All Public Entries",
    description=(
        """
### Functionality
This endpoint retrieves all `PUBLIC` entries known to the node,
regardless of the author.

### When to Use
Use this to get a feed of all public content on the node. This is
useful for unauthenticated users or a public timeline view that shows
activity across the entire server.

### How to Use
- Send a GET request to this endpoint. No authentication is required.
- Pagination is supported using `?page=<number>` and `?size=<number>`.

### Visibility Rules
- This endpoint **only** returns entries explicitly marked as `PUBLIC`.
  It will not show `FRIENDS` or `UNLISTED` entries.
"""
    ),
    responses={
        200: OpenApiResponse(
            response=EntryListSerializer,
            description=(
                "A paginated list of all public entries "
                "was retrieved."
            ),
            examples=[
                OpenApiExample(
                    "Successful Public Entries Response",
                    value={
                        "type": "entries",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "src": [
                            {
                                "type": "entry",
                                "title": "Hello",
                                "id":
                                    "http://127.0.0.1:8000/api/authors/"
                                    "1ca872dc-7664-4622-b21c-"
                                    "d3c25e5cd3cc/"
                                    "entries/"
                                    "87dd3f77-5a3d-4929-a523-"
                                    "b692cb333fa9",
                                "web":
                                    "http://127.0.0.1:8000/authors/"
                                    "1ca872dc-7664-4622-b21c-"
                                    "d3c25e5cd3cc/"
                                    "entries/"
                                    "87dd3f77-5a3d-4929-a523-"
                                    "b692cb333fa9",
                                "description": "",
                                "contentType": "text/plain",
                                "content": "I am A",
                                "author": {
                                    "type": "author",
                                    "id":
                                        "http://127.0.0.1:8000/api/authors/"
                                        "1ca872dc-7664-4622-"
                                        "b21c-d3c25e5cd3cc/",
                                    "host": "http://127.0.0.1:8000/",
                                    "displayName": "a",
                                    "github": "",
                                    "profileImage": "",
                                    "web":
                                        "http://127.0.0.1:8000/"
                                        "authors/"
                                        "1ca872dc-7664-4622-"
                                        "b21c-d3c25e5cd3cc/",
                                    "followers_count": 0,
                                    "following_count": 1,
                                    "friends_count": 0
                                },
                                "comments": {
                                    "type": "comments",
                                    "id":
                                        "http://127.0.0.1:8000/api/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-"
                                        "b692cb333fa9/"
                                        "comments",
                                    "web":
                                        "http://127.0.0.1:8000/authors/"
                                        "1ca872dc-7664-4622-b21c-"
                                        "d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-"
                                        "b692cb333fa9/"
                                        "comments",
                                    "page_number": 1,
                                    "size": 5,
                                    "count": 0,
                                    "src": []
                                },
                                "likes": {
                                    "type": "likes",
                                    "id":
                                        "http://127.0.0.1:8000/api/authors/"
                                        "1ca872dc-7664-4622-"
                                        "b21c-d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-"
                                        "b692cb333fa9/"
                                        "likes",
                                    "web":
                                        "http://127.0.0.1:8000/authors/"
                                        "1ca872dc-7664-4622-"
                                        "b21c-d3c25e5cd3cc/"
                                        "entries/"
                                        "87dd3f77-5a3d-4929-a523-"
                                        "b692cb333fa9/"
                                        "likes",
                                    "page_number": 1,
                                    "size": 5,
                                    "count": 0,
                                    "src": []
                                },
                                "published":
                                    "2025-06-22T23:35:17.231226-06:00",
                                "visibility": "PUBLIC"
                            }
                        ]
                    }
                )
            ]
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
    tags=['Entries']
)
class PublicEntryListView(generics.ListAPIView):
    """
    GET: List all public entries known to the node.
    """
    serializer_class = EntrySerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """
        Return a list of all public entries from all authors
        known to the node.
        """
        return Entry.objects.filter(
            visibility='PUBLIC', is_deleted=False
        ).order_by('-published')

    def list(self, request, *args, **kwargs):
        """
        Match the proper 'entries' object format.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "entries",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "src": paginated_data['results'],
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "entries",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "src": serializer.data
        })


@extend_schema(
    summary="List Author's Entries or Create a New One",
    description=(
        """
### Functionality
This endpoint handles two main operations for an author's entries:
- **GET**: Retrieves a list of entries belonging to a specific author.
- **POST**: Creates a new entry for the currently authenticated author.

### When to Use
- **GET**: Use this to display an author's feed or list of posts. The
  entries returned are filtered based on their `visibility` and the
  relationship between the viewer and the author (e.g., friends,
  followers, public).
- **POST**: Use this when a user wants to publish a new post. The
  authenticated user must match the author specified in the URL.

### How to Use
- **GET**: Simply send a GET request to the URL. Pagination is
  supported using `?page=<number>` and `?size=<number>`.
- **POST**: Send a POST request with the entry data in the request
  body. The `author` field is automatically set to the authenticated
  user.

### Visibility Rules (for GET)
- **Public**: Visible to everyone.
- **Friends**: Visible only to users who are mutual followers with the
  author.
- **Unlisted**: Not listed on public feeds but accessible via direct
  link.
- If you are the author, you see all your posts regardless of
  visibility.
"""
    ),
    examples=[
        OpenApiExample(
            "POST Request to Create a Text Entry",
            request_only=True,
            value={
                "title": "A Post About My Day",
                "description": "A short summary of what I did today.",
                "visibility": "PUBLIC",
                "contentType": "text/plain",
                "content": "Today, I learned how to document an API..."
            }
        ),
        OpenApiExample(
            "POST Request to Create an Image Entry",
            request_only=True,
            value={
                "title": "A Picture from My Trip",
                "description": "A beautiful sunset I saw.",
                "visibility": "FRIENDS",
                "contentType": "image/jpeg;base64",
                "content": "/9j/4AAQSkZJRgABAQEASABIAAD..."
            }
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=EntryListSerializer,
            description="A paginated list of entries was retrieved.",
            examples=[
                OpenApiExample(
                    "Successful GET Response",
                    value={
                        "type": "entries",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "src": [
                            {
                                "type": "entry",
                                "title": "My First Post",
                                "id": (
                                    "http://host/api/authors/{author_id}/"
                                    "entries/{entry_id}"
                                ),
                                "web": (
                                    "http://host/authors/{author_id}/"
                                    "entries/{entry_id}"
                                ),
                                "description": "A short summary.",
                                "contentType": "text/plain",
                                "content": "The full content.",
                                "author": {
                                    "type": "author",
                                    "id": (
                                        "http://host/api/authors/"
                                        "{author_id}"
                                    ),
                                    "host": "http://host/",
                                    "displayName": "Author Name",
                                    "github": "http://github.com/author",
                                    "profileImage": (
                                        "https://i.imgur.com/k7XVwpB.jpeg"
                                    )
                                },
                                "comments": {
                                    "type": "comments",
                                    "id": (
                                        "http://host/api/authors/"
                                        "{author_id}/entries/{entry_id}/"
                                        "comments"
                                    ),
                                    "web": (
                                        "http://host/authors/{author_id}/"
                                        "entries/{entry_id}/comments"
                                    ),
                                    "page_number": 1,
                                    "size": 5,
                                    "count": 0,
                                    "src": []
                                },
                                "likes": {
                                    "type": "likes",
                                    "id": (
                                        "http://host/api/authors/"
                                        "{author_id}/entries/{entry_id}/"
                                        "likes"
                                    ),
                                    "web": (
                                        "http://host/authors/{author_id}/"
                                        "entries/{entry_id}/likes"
                                    ),
                                    "page_number": 1,
                                    "size": 5,
                                    "count": 0,
                                    "src": []
                                },
                                "published": "2024-03-28T12:00:00Z",
                                "visibility": "PUBLIC"
                            }
                        ]
                    }
                )
            ]
        ),
        201: OpenApiResponse(
            response=EntrySerializer,
            description="Entry created successfully."
        ),
    },
    parameters=[
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                'A page number within the paginated result set. '
                'Only for GET requests.'
            )
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                'Number of results to return per page. '
                'Only for GET requests.'
            )
        ),
    ],
    tags=['Entries']
)
class EntryListView(generics.ListCreateAPIView):
    """
    GET: List entries for a given author, filtered by visibility.
    POST: Create a new entry for the currently authenticated author.
    """
    serializer_class = EntrySerializer
    permission_classes = [EntryPermission]
    pagination_class = StandardPagination

    def get_queryset(self):
        # This method remains the same
        author_serial = self.kwargs['author_serial']
        author = get_object_or_404(Author, serial=author_serial)
        queryset = Entry.objects.filter(author=author, is_deleted=False)
        if self.request.user.is_authenticated and self.request.user == author:
            return queryset.order_by('-published')
        if self.request.user.is_authenticated:
            if self.request.user.is_friend_with(author):
                return queryset.filter(
                    visibility__in=['PUBLIC', 'UNLISTED', 'FRIENDS']
                ).order_by('-published')
            elif self.request.user.is_following(author):
                return queryset.filter(
                    visibility__in=['PUBLIC', 'UNLISTED']
                ).order_by('-published')
        return queryset.filter(visibility='PUBLIC').order_by('-published')

    def perform_create(self, serializer):
        # This method remains the same
        author = get_object_or_404(Author, serial=self.kwargs['author_serial'])
        serializer.save(author=author)

    def list(self, request, *args, **kwargs):
        """
        Override to match the spec's 'entries' object format and to poll
        GitHub for events.
        """
        # Generated by Genmin 2.5pro 2025-07-07
        author = get_object_or_404(Author, serial=self.kwargs['author_serial'])
        process_github_events(author)

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "entries",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "src": paginated_data['results'],
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "entries",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "src": serializer.data
        })


@extend_schema(
    summary="Retrieve, Update, or Delete a Single Entry",
    description=(
        """
### Functionality
This endpoint manages a single entry and supports:
- **GET**: Retrieving the full details of one entry.
- **PUT/PATCH**: Updating an existing entry's content or properties.
- **DELETE**: Marking an entry as deleted (soft delete).

### When to Use
- **GET**: When a user clicks to view a specific post. Access is
  controlled by the entry's `visibility` setting.
- **PUT/PATCH**: To allow an author to edit their own post.
- **DELETE**: To allow an author to remove their own post. The entry is
  not permanently removed from the database but is hidden from all
  views.

### How to Use
- **GET**: The general public can view `PUBLIC` entries. Friends can
  view `FRIENDS` entries. The author can view all their entries.
- **PUT/PATCH**: Authenticate as the author of the entry and send a
  request with the fields to be updated in the body.
- **DELETE**: Authenticate as the author and send a DELETE request.
  The response will have no content.

### Permissions
- Only the author of the entry can update or delete it.
- Viewing permissions are based on the entry's `visibility` and the
  viewer's relationship with the author.
"""
    ),
    examples=[
        OpenApiExample(
            "PUT/PATCH Request to Update an Entry",
            request_only=True,
            value={
                "title": "An Updated Title",
                "visibility": "FRIENDS",
                "content": "I've edited the content of this post."
            }
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=EntrySerializer,
            description="Entry retrieved or updated successfully.",
        ),
        204: OpenApiResponse(description="Entry successfully deleted."),
        403: OpenApiResponse(description="Permission denied."),
        404: OpenApiResponse(description="Entry not found.")
    },
    tags=['Entries']
)
class EntryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a single entry.
    PUT/PATCH: Update an entry.
    DELETE: Mark an entry as deleted (soft delete).
    """
    serializer_class = EntrySerializer
    permission_classes = [EntryPermission]
    lookup_field = 'serial'
    lookup_url_kwarg = 'entry_serial'

    def get_queryset(self):
        """
        This view should return an object for a specific entry,
        determined by the author_serial and entry_serial portions of the URL.
        """

        entry_serial = self.kwargs['entry_serial']
        # We only look for entries by the specified author
        # that are not deleted.
        # The permission class will handle visibility checks.
        result = Entry.objects.filter(
            serial=entry_serial, is_deleted=False
        )
        return result

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        """
        Instead of deleting the entry from the database, mark it as deleted.
        This will trigger distribution to all previously notified followers.
        """
        instance.is_deleted = True
        instance.visibility = 'DELETED'
        instance.save()  # This triggers the post_save signal for distribution


@extend_schema(
    summary="List or Create Comments on an Entry",
    description=(
        """
### Functionality
- **GET**: Retrieves a paginated list of comments for a specific entry.
- **POST**: Adds a new comment to an entry on behalf of the
  authenticated user.

### When to Use
- **GET**: To load and display the comment section for a post.
- **POST**: When a user submits a new comment.

### How to Use
- **GET**: The endpoint is paginated (`?page=<number>`, `?size=<number>`).
- **POST**: Send a JSON object with the `comment` content. The `author`
  is automatically set to the authenticated user.

### Visibility Rules
A key feature of this endpoint is its handling of comments on
`FRIENDS` visibility entries.
- If a post is for `FRIENDS` only, you will only see comments made by
  the post's author and your own comments. You **cannot** see comments
  from other friends of the author unless you are also friends with them.
- For all other visibilities, if you can see the entry, you can see all
  the comments.
"""
    ),
    examples=[
        OpenApiExample(
            "POST Request to Add a Comment",
            request_only=True,
            value={
                "comment": "This is a very insightful post!",
                "contentType": "text/plain"
            }
        ),
    ],
    request=inline_serializer(
        name='CommentCreationSerializer',
        fields={
            'comment': serializers.CharField(
                help_text="The content of the comment."
            ),
            'contentType': serializers.CharField(
                default='text/plain',
                help_text="The MIME type of the comment, e.g., "
                          "'text/plain' or 'text/markdown'."
            ),
        },
    ),
    responses={
        "200": OpenApiResponse(
            response=CommentListResponseSerializer,
            description="A paginated list of comments was retrieved.",
            examples=[
                OpenApiExample(
                    "GET Response for Comments",
                    value={
                        "type": "comments",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "id": (
                            "http://host/api/authors/{author_id}/entries/"
                            "{entry_id}/comments"
                        ),
                        "web": (
                            "http://host/authors/{author_id}/entries/"
                            "{entry_id}/comments"
                        ),
                        "src": [{
                            "type": "comment",
                            "author": {
                                "type": "author",
                                "id": (
                                    "http://host/api/authors/"
                                    "{commenter_id}"
                                ),
                                "host": "http://host/",
                                "displayName": "Commenter Name",
                                "github": "http://github.com/commenter",
                                "profileImage": (
                                    "https://i.imgur.com/k7XVwpB.jpeg"
                                )
                            },
                            "comment": "This is a great comment!",
                            "contentType": "text/plain",
                            "published": "2024-03-28T12:05:00Z",
                            "id": (
                                "http://host/api/authors/{commenter_id}/"
                                "commented/{comment_id}"
                            ),
                            "web": (
                                "http://host/authors/{author_id}/"
                                "entries/{entry_id}"
                            ),
                            "entry": (
                                "http://host/api/authors/{author_id}/"
                                "entries/{entry_id}"
                            ),
                            "likes": {
                                "type": "likes",
                                "id": (
                                    "http://host/api/authors/"
                                    "{commenter_id}/commented/"
                                    "{comment_id}/likes"
                                ),
                                "page_number": 1,
                                "size": 5,
                                "count": 0,
                                "src": []
                            },
                            "serial": "{comment_id}"
                        }]
                    }
                )
            ]
        ),
        "201": OpenApiResponse(
            response=CommentSerializer,
            description="Comment created successfully."
        ),
    },
    parameters=[
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                'A page number within the paginated result set. '
                'Only for GET requests.'
            )
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                'Number of results to return per page. '
                'Only for GET requests.'
            )
        ),
    ],
    tags=['Comments']
)
class CommentListView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [CanAccessContentPermission]
    pagination_class = StandardPagination

    # KEY adjustments to get_queryset FOR USER STORY 7.4
    # Example that should work for this user story:
    # Person 1 makes a friend-only post, Person 2 and Person 3
    # are friends with Person 1, but Person 2 and Person 3
    # are not friends with each other
    # If person 2 makes a comment on this friend-only post, Person 3 should
    # not be able to see the comment since hes not friends with Person 2
    def get_queryset(self):
        entry_serial = self.kwargs['entry_serial']
        entry = get_object_or_404(Entry, serial=entry_serial)
        qs = Comment.objects.filter(entry=entry).order_by('-published')

        if entry.visibility == 'FRIENDS':
            # If viewer is the author of the entry, show all comments
            if self.request.user == entry.author:
                return qs

            # Otherwise, only show comments by the entry author or the viewer
            allowed_authors = [entry.author, self.request.user]
            qs = qs.filter(author__in=allowed_authors)

        return qs

    def perform_create(self, serializer):
        entry_serial = self.kwargs['entry_serial']
        entry = get_object_or_404(Entry, serial=entry_serial)
        serializer.save(entry=entry, author=self.request.user)

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'comments' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        entry_serial = self.kwargs['entry_serial']
        entry = get_object_or_404(Entry, serial=entry_serial)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "comments",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "id": f"{entry.get_api_url()}/comments",
                "web": f"{entry.get_web_url()}/comments",
                "src": paginated_data['results']
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "comments",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "id": f"{entry.get_api_url()}/comments",
            "web": f"{entry.get_web_url()}/comments",
            "src": serializer.data,
        })


@extend_schema(
    summary="List or Create Likes on an Entry",
    description=(
        """
### Functionality
- **GET**: Retrieves a paginated list of 'like' objects for a specific
  entry.
- **POST**: Creates a 'like' on the entry for the currently
  authenticated user.

### When to Use
- **GET**: To display who has liked a particular entry.
- **POST**: When a user clicks a "like" button on an entry.

### How to Use
- **GET**: The endpoint is paginated (`?page=<number>`, `?size=<number>`).
  Access to the list of likes depends on your ability to view the
  parent entry.
- **POST**: Send an empty POST request. The `author` of the like is
  automatically set to the authenticated user. You can only like an
  entry once.
"""
    ),
    request=None,
    responses={
        200: OpenApiResponse(
            response=LikeListResponseSerializer,
            description="A paginated list of likes was retrieved.",
            examples=[
                OpenApiExample(
                    "GET Response for Likes",
                    value={
                        "type": "likes",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "id": (
                            "http://host/api/authors/{author_id}/"
                            "entries/{entry_id}/likes"
                        ),
                        "web": (
                            "http://host/authors/{author_id}/"
                            "entries/{entry_id}/likes"
                        ),
                        "src": [
                            {
                                "type": "like",
                                "author": {
                                    "type": "author",
                                    "id": (
                                        "http://host/api/authors/"
                                        "{liker_id}"
                                    ),
                                    "host": "http://host/",
                                    "displayName": "Liker Name",
                                    "github": "http://github.com/liker",
                                    "profileImage": (
                                        "https://i.imgur.com/k7XVwpB.jpeg"
                                    )
                                },
                                "object": (
                                    "http://host/api/authors/{author_id}/"
                                    "entries/{entry_id}"
                                ),
                                "published": "2024-03-28T12:01:00Z",
                                "id": (
                                    "http://host/api/authors/{liker_id}/"
                                    "liked/{like_id}"
                                )
                            }
                        ]
                    }
                )
            ]
        ),
        201: OpenApiResponse(
            response=LikeSerializer,
            description="Like created successfully."
        ),
    },
    parameters=[
        OpenApiParameter(
            name='page',
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                'A page number within the paginated result set. '
                'Only for GET requests.'
            )
        ),
        OpenApiParameter(
            name='size',
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                'Number of results to return per page. '
                'Only for GET requests.'
            )
        ),
    ],
    tags=['Likes']
)
class LikeListOnEntryView(generics.ListCreateAPIView):
    """
    GET: List all likes on a specific entry.
    POST:Allows to like a specific entry(perform_create)
    """
    serializer_class = LikeSerializer
    permission_classes = [CanAccessContentPermission]
    pagination_class = StandardPagination

    def get_queryset(self):
        """
        Return a list of all likes for the entry as determined by the
        author_serial and entry_serial portions of the URL.
        """
        entry_serial = self.kwargs['entry_serial']
        entry = get_object_or_404(Entry, serial=entry_serial)
        entry_content_type = ContentType.objects.get_for_model(Entry)
        return Like.objects.filter(
            content_type=entry_content_type,
            object_id=entry.url
        ).order_by('-published')

    def perform_create(self, serializer):
        entry_serial = self.kwargs['entry_serial']
        entry = get_object_or_404(Entry, serial=entry_serial)
        content_type = ContentType.objects.get_for_model(Entry)

        # Generate a unique serial and URL for the like
        like_serial = uuid.uuid4()
        like_url = f"{
            self.request.user.host.rstrip('/')}/api/authors/{
            self.request.user.serial}/liked/{like_serial}/"

        serializer.save(
            url=like_url,
            serial=like_serial,
            author=self.request.user,
            content_type=content_type,
            object_id=entry.url
        )

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'likes' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        entry_serial = self.kwargs['entry_serial']
        entry = get_object_or_404(Entry, serial=entry_serial)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "likes",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "id": f"{entry.get_api_url()}/likes",
                "web": f"{entry.get_web_url()}/likes",
                "src": paginated_data['results']
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "likes",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "id": f"{entry.get_api_url()}/likes",
            "web": f"{entry.get_web_url()}/likes",
            "src": serializer.data
        })


@extend_schema(
    summary="List Likes on a Comment",
    description=(
        """
### Functionality
- **GET**: Retrieves a paginated list of 'like' objects for a specific
  comment.

### When to Use
- To display who has liked a particular comment on an entry.

### How to Use
- The endpoint is paginated (`?page=<number>`, `?size=<number>`).
- Access to the list of likes depends on your ability to view the
  parent entry where the comment was made.
"""
    ),
    responses={
        200: OpenApiResponse(
            response=LikeListResponseSerializer,
            description=(
                "A paginated list of likes for a comment was retrieved."
            ),
            examples=[
                OpenApiExample(
                    "GET Response for Likes on a Comment",
                    value={
                        "type": "likes",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "id": (
                            "http://host/api/authors/{author_id}/entries/"
                            "{entry_id}/comments/{comment_id}/likes"
                        ),
                        "web": (
                            "http://host/authors/{author_id}/entries/"
                            "{entry_id}"
                        ),
                        "src": [
                            {
                                "type": "like",
                                "author": {
                                    "type": "author",
                                    "id": (
                                        "http://host/api/authors/{liker_id}"
                                    ),
                                    "host": "http://host/",
                                    "displayName": "Liker Name",
                                    "github": "http://github.com/liker",
                                    "profileImage": (
                                        "https://i.imgur.com/k7XVwpB.jpeg"
                                    )
                                },
                                "object": (
                                    "http://host/api/authors/{author_id}/"
                                    "entries/{entry_id}/comments/"
                                    "{comment_id}"
                                ),
                                "published": "2024-03-28T12:02:00Z",
                                "id": (
                                    "http://host/api/authors/{liker_id}/"
                                    "liked/{like_id}"
                                )
                            }
                        ]
                    }
                )
            ]
        ),
        201: OpenApiResponse(
            response=LikeSerializer,
            description="Like created successfully."
        ),
        400: OpenApiResponse(
            description=(
                "Bad Request. The user may have already liked this comment."
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
    tags=['Likes']
)
class LikeListOnCommentView(generics.ListCreateAPIView):
    """
    GET: List all likes for a specific comment.
    POST: Create a new like on a specific comment.
    """
    serializer_class = LikeSerializer
    permission_classes = [CanAccessContentPermission]
    pagination_class = StandardPagination

    def get_queryset(self):
        comment_serial = self.kwargs['comment_serial']
        comment = get_object_or_404(Comment, serial=comment_serial)
        # Return all likes for this comment
        return Like.objects.filter(
            object_id=comment.url,
            content_type=ContentType.objects.get_for_model(Comment)
        ).order_by('-published')

    def perform_create(self, serializer):
        """
        Create a new like on the comment specified in the URL.
        The user must have permission to view the parent entry.
        """
        comment_serial = self.kwargs['comment_serial']
        comment = get_object_or_404(Comment, serial=comment_serial)

        # The permission class already checks if the user can view the
        # parent entry.

        # Check if the user has already liked this comment
        content_type = ContentType.objects.get_for_model(Comment)
        if Like.objects.filter(
            author=self.request.user,
            object_id=comment.url,
            content_type=content_type
        ).exists():
            raise serializers.ValidationError(
                "You have already liked this comment.", code='conflict')

        # Generate a unique serial and URL for the like
        like_serial = uuid.uuid4()
        like_url = f"{
            self.request.user.host.rstrip('/')}/api/authors/{
            self.request.user.serial}/liked/{like_serial}/"

        serializer.save(
            url=like_url,
            serial=like_serial,
            author=self.request.user,
            content_object=comment
        )

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'likes' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        comment_serial = self.kwargs['comment_serial']
        comment = get_object_or_404(Comment, serial=comment_serial)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "likes",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "id": f"{comment.get_api_url()}/likes",
                "web": f"{comment.entry.get_web_url()}",
                "src": paginated_data['results']
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "likes",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "id": f"{comment.get_api_url()}/likes",
            "web": f"{comment.entry.get_web_url()}",
            "src": serializer.data
        })


@extend_schema(
    summary="Get an Entry by its FQID",
    description=(
        """
### Functionality
- **GET**: Retrieve a single entry using its Fully-Qualified ID (FQID).
  An FQID is the absolute, globally unique URL that identifies the
  entry.

### When to Use
- Use this endpoint when you have the full URL of an entry (e.g., from
  a 'like' object or an external source) and need to fetch its
  details directly, without knowing the author's serial separately.

### How to Use
- The `entry_fqid` in the path must be the URL-encoded FQID of the
  entry. For example, the FQID
  `http://host/api/authors/{author_id}/entries/{entry_id}`
  would be passed in the URL.
- Access to the entry is subject to the same visibility and permission
  rules as the standard entry detail endpoint.
"""
    ),
    responses={
        200: OpenApiResponse(
            response=EntrySerializer,
            description="Entry was retrieved successfully.",
        ),
        403: OpenApiResponse(description="Permission denied."),
        404: OpenApiResponse(
            description="Entry not found or FQID is malformed."
        )
    },
    tags=['Entries (FQID)']
)
class EntryByFQIDView(generics.RetrieveAPIView):
    """
    GET /api/entries/{ENTRY_FQID}/ - get entry by FQID
    Supports visibility controls and authentication
    """
    serializer_class = EntrySerializer
    permission_classes = [EntryPermission]

    def get_object(self):
        """Parse FQID and retrieve entry with permission checks"""
        entry_fqid = self.kwargs['entry_fqid']

        # Parse the FQID to get the entry
        entry = parse_entry_fqid(entry_fqid)

        # Check object permissions using existing permission class
        self.check_object_permissions(self.request, entry)

        return entry


@extend_schema(
    summary="List Comments on an Entry by its FQID",
    description=(
        """
### Functionality
- **GET**: Retrieves a paginated list of comments for an entry that is
  identified by its FQID.

### When to Use
- When you have the FQID of an entry and need to retrieve its comments
  without knowing the author's serial separately. This is useful when
  navigating from an object that only provides the entry's full URL.

### How to Use
- The `entry_fqid` in the path must be the URL-encoded FQID of the
  entry.
- The endpoint is paginated (`?page=<number>`, `?size=<number>`).
- Access to the comments is subject to your permission to view the
  parent entry. The same visibility rules as the standard comment list
  endpoint apply.
"""
    ),
    responses={
        200: OpenApiResponse(
            response=CommentListResponseSerializer,
            description="A paginated list of comments was retrieved.",
            examples=[
                OpenApiExample(
                    "GET Response for Comments",
                    value={
                        "type": "comments",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "id": (
                            "http://host/api/authors/{author_id}/entries/"
                            "{entry_id}/comments"
                        ),
                        "web": (
                            "http://host/authors/{author_id}/entries/"
                            "{entry_id}/comments"
                        ),
                        "src": [{
                            "type": "comment",
                            "author": {
                                "type": "author",
                                "id": (
                                    "http://host/api/authors/"
                                    "{commenter_id}"
                                ),
                                "host": "http://host/",
                                "displayName": "Commenter Name",
                                "github": "http://github.com/commenter",
                                "profileImage": (
                                    "https://i.imgur.com/k7XVwpB.jpeg"
                                )
                            },
                            "comment": "This is a great comment!",
                            "contentType": "text/plain",
                            "published": "2024-03-28T12:05:00Z",
                            "id": (
                                "http://host/api/authors/{commenter_id}/"
                                "commented/{comment_id}"
                            ),
                            "web": (
                                "http://host/authors/{author_id}/"
                                "entries/{entry_id}"
                            ),
                            "entry": (
                                "http://host/api/authors/{author_id}/"
                                "entries/{entry_id}"
                            ),
                            "likes": {
                                "type": "likes",
                                "id": (
                                    "http://host/api/authors/"
                                    "{commenter_id}/commented/"
                                    "{comment_id}/likes"
                                ),
                                "page_number": 1,
                                "size": 5,
                                "count": 0,
                                "src": []
                            },
                            "serial": "{comment_id}"
                        }]
                    }
                )
            ]
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
    tags=['Comments (FQID)']
)
class CommentsByEntryFQIDView(generics.ListAPIView):
    """
    GET /api/entries/{ENTRY_FQID}/comments/ - get comments on entry by FQID
    Uses the same permission logic as regular comment endpoints
    """
    serializer_class = CommentSerializer
    permission_classes = [FQIDBasedPermission]
    pagination_class = StandardPagination

    _entry_cache = None

    def get_entry(self):
        """Parse FQID and get the entry, caching the result for the request."""
        if self._entry_cache is None:
            entry_fqid = self.kwargs['entry_fqid']
            self._entry_cache = parse_entry_fqid(entry_fqid)
        return self._entry_cache

    def get_queryset(self):
        """Get comments for the entry identified by FQID"""
        entry = self.get_entry()

        # Check object permissions explicitly
        self.check_object_permissions(self.request, entry)

        return Comment.objects.filter(entry=entry).order_by('-published')

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'comments' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        entry = self.get_entry()

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "comments",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "id": f"{entry.get_api_url()}/comments",
                "web": f"{entry.get_web_url()}/comments",
                "src": paginated_data['results']
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "comments",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "id": f"{entry.get_api_url()}/comments",
            "web": f"{entry.get_web_url()}/comments",
            "src": serializer.data
        })


@extend_schema(
    summary="List Likes on an Entry by its FQID",
    description=(
        """
### Functionality
- **GET**: Retrieves a paginated list of likes for an entry that is
  identified by its FQID.

### When to Use
- When you have the FQID of an entry and need to retrieve its likes
  without knowing the author's serial separately.

### How to Use
- The `entry_fqid` in the path must be the URL-encoded FQID of the
  entry.
- The endpoint is paginated (`?page=<number>`, `?size=<number>`).
- Access to the likes is subject to your permission to view the
  parent entry.
"""
    ),
    responses={
        200: OpenApiResponse(
            response=LikeListResponseSerializer,
            description="A paginated list of likes was retrieved.",
            examples=[
                OpenApiExample(
                    "GET Response for Likes",
                    value={
                        "type": "likes",
                        "page_number": 1,
                        "size": 1,
                        "count": 1,
                        "id": (
                            "http://host/api/authors/{author_id}/"
                            "entries/{entry_id}/likes"
                        ),
                        "web": (
                            "http://host/authors/{author_id}/"
                            "entries/{entry_id}/likes"
                        ),
                        "src": [
                            {
                                "type": "like",
                                "author": {
                                    "type": "author",
                                    "id": (
                                        "http://host/api/authors/"
                                        "{liker_id}"
                                    ),
                                    "host": "http://host/",
                                    "displayName": "Liker Name",
                                    "github": "http://github.com/liker",
                                    "profileImage": (
                                        "https://i.imgur.com/k7XVwpB.jpeg"
                                    )
                                },
                                "object": (
                                    "http://host/api/authors/{author_id}/"
                                    "entries/{entry_id}"
                                ),
                                "published": "2024-03-28T12:01:00Z",
                                "id": (
                                    "http://host/api/authors/{liker_id}/"
                                    "liked/{like_id}"
                                )
                            }
                        ]
                    }
                )
            ]
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
    tags=['Likes (FQID)']
)
class LikesByEntryFQIDView(generics.ListAPIView):
    """
    GET /api/entries/{ENTRY_FQID}/likes/ - get likes on entry by FQID
    Uses the same permission logic as regular like endpoints
    """
    serializer_class = LikeSerializer
    permission_classes = [FQIDBasedPermission]
    pagination_class = StandardPagination

    _entry_cache = None

    def get_entry(self):
        """Parse FQID and get the entry, caching the result for the request."""
        if self._entry_cache is None:
            entry_fqid = self.kwargs['entry_fqid']
            self._entry_cache = parse_entry_fqid(entry_fqid)
        return self._entry_cache

    def get_queryset(self):
        """Get likes for the entry identified by FQID"""
        entry = self.get_entry()

        # Check object permissions explicitly
        self.check_object_permissions(self.request, entry)

        entry_content_type = ContentType.objects.get_for_model(Entry)
        return Like.objects.filter(
            content_type=entry_content_type,
            object_id=entry.url
        ).order_by('-published')

    def list(self, request, *args, **kwargs):
        """Override to match the spec's 'likes' object format."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        entry = self.get_entry()

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_data = self.get_paginated_response(serializer.data).data
            return Response({
                "type": "likes",
                "page_number": self.paginator.page.number,
                "size": len(paginated_data['results']),
                "count": paginated_data['count'],
                "id": f"{entry.get_api_url()}/likes",
                "web": f"{entry.get_web_url()}/likes",
                "src": paginated_data['results']
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "type": "likes",
            "page_number": 1,
            "size": queryset.count(),
            "count": queryset.count(),
            "id": f"{entry.get_api_url()}/likes",
            "web": f"{entry.get_web_url()}/likes",
            "src": serializer.data
        })


@extend_schema(
    summary="Retrieve an Image Entry by FQID",
    description=(
        """
### Functionality
- **GET**: Retrieves the raw image content of an entry identified by its
  FQID. This endpoint is specifically for entries where the
  `contentType` is an image type (e.g., `image/jpeg;base64` or
  `image/png;base64`).

### When to Use
- To display an image from an image post directly, for example, in an
  `<img>` tag in a web browser.

### How to Use
- The `entry_fqid` must be the URL-encoded FQID of an image entry.
- The response will not be JSON, but the binary data of the image
  with the appropriate `Content-Type` header (e.g., `image/jpeg`).
- Access is subject to the entry's visibility settings.
"""
    ),
    responses={
        (200, 'image/png'): OpenApiResponse(
            description="The PNG image data.",
            response=bytes,
        ),
        (200, 'image/jpeg'): OpenApiResponse(
            description="The JPEG image data.",
            response=bytes,
        ),
        (200, 'application/base64'): OpenApiResponse(
            description="The base64-encoded image data.",
            response=bytes,
        ),
        403: OpenApiResponse(description="Permission denied."),
        404: OpenApiResponse(
            description="Image entry not found or entry is not an image."
        )
    },
    tags=['Entries (FQID)']
)
class ImageEntryByFQIDView(generics.RetrieveAPIView):
    serializer_class = EntrySerializer
    permission_classes = [EntryPermission]

    def retrieve(self, request, *args, **kwargs):
        """Parse FQID and retrieve entry with permission checks"""
        entry_fqid = kwargs['entry_fqid']

        # Parse the FQID to get the entry
        entry = parse_entry_fqid(entry_fqid)

        # Check object permissions using existing permission class
        self.check_object_permissions(request, entry)

        print(entry.content_type)
        match entry.content_type:
            case ("image/jpeg;base64" | "image/png;base64" |
                  "application/base64"):
                image_data = base64.b64decode(entry.content)
                return HttpResponse(
                    image_data,
                    content_type=get_response_image_content_type(entry.content)
                )
            case _:
                raise Http404("Cannot find image entry with given entry FQID.")


@extend_schema(
    summary="Retrieve an Image Entry by Serials",
    description=(
        """
### Functionality
- **GET**: Retrieves the raw image content of an entry, identified by
  the author's and the entry's serials (UUIDs). This endpoint is for
  entries where `contentType` is an image type.

### When to Use
- This is the standard endpoint for directly displaying an image from a
  post when you have the author and entry IDs. It's suitable for use
  in `<img>` tags.

### How to Use
- The response will be the binary data of the image with the
  appropriate `Content-Type` header (e.g., `image/jpeg`), not JSON.
- Access is subject to the entry's visibility settings.
"""
    ),
    responses={
        (200, 'image/png'): OpenApiResponse(
            description="The PNG image data.",
            response=bytes,
        ),
        (200, 'image/jpeg'): OpenApiResponse(
            description="The JPEG image data.",
            response=bytes,
        ),
        (200, 'application/base64'): OpenApiResponse(
            description="The base64-encoded image data.",
            response=bytes,
        ),
        403: OpenApiResponse(description="Permission denied."),
        404: OpenApiResponse(
            description="Image entry not found or entry is not an image."
        )
    },
    tags=['Entries']
)
class AuthorEntryImageView(generics.RetrieveAPIView):
    serializer_class = EntrySerializer
    permission_classes = [EntryPermission]

    def retrieve(self, request, *args, **kwargs):
        author_serial = kwargs['author_serial']
        entry_serial = kwargs['entry_serial']

        entry = get_object_or_404(
            Entry,
            serial=entry_serial,
            author__serial=author_serial,
            is_deleted=False
        )

        match entry.content_type:
            case ("image/jpeg;base64" | "image/png;base64" |
                  "application/base64"):
                image_data = base64.b64decode(entry.content)
                return HttpResponse(
                    image_data,
                    content_type=get_response_image_content_type(entry.content)
                )
            case _:
                raise Http404("Cannot find image entry with given serials.")
