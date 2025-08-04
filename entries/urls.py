from django.urls import path
from . import views

app_name = "entries"

# Order matters
# More specific paths must come before the general one to ensure correct
# URL matching.
urlpatterns = [
    # Stream endpoint
    path(
        'stream/',
        views.StreamView.as_view(),
        name='stream'
    ),

    # Entry endpoints
    path(
        'entries/',
        views.PublicEntryListView.as_view(),
        name='public-entry-list'
    ),
    path(
        'authors/<uuid:author_serial>/entries/',
        views.EntryListView.as_view(),
        name='entry-list'
    ),
    path(
        'authors/<uuid:author_serial>/entries/<uuid:entry_serial>/',
        views.EntryDetailView.as_view(),
        name='entry-detail'
    ),

    # Image endpoints
    path(
        'entries/<path:entry_fqid>/image',
        views.ImageEntryByFQIDView.as_view(),
        name='image-entry-by-fqid'
    ),

    path(
        'authors/<uuid:author_serial>/entries/<uuid:entry_serial>/image',
        views.AuthorEntryImageView.as_view(),
        name="author-entry-image"
    ),

    # FQID-based entry endpoints
    path(
        'entries/<path:entry_fqid>/comments/',
        views.CommentsByEntryFQIDView.as_view(),
        name='comments-by-entry-fqid'
    ),
    path(
        'entries/<path:entry_fqid>/likes/',
        views.LikesByEntryFQIDView.as_view(),
        name='likes-by-entry-fqid'
    ),
    path(
        'entries/<path:entry_fqid>/',
        views.EntryByFQIDView.as_view(),
        name='entry-by-fqid'
    ),

    # Comments and Likes list endpoints
    path(
        'authors/<uuid:author_serial>/entries/<uuid:entry_serial>/comments/',
        views.CommentListView.as_view(),
        name='comment-list-on-entry'
    ),
    path(
        'authors/<uuid:author_serial>/entries/<uuid:entry_serial>/likes/',
        views.LikeListOnEntryView.as_view(),
        name='like-list-on-entry'
    ),
    path(
        'authors/<uuid:author_serial>/entries/<uuid:entry_serial>/comments/'
        '<uuid:comment_serial>/likes/',
        views.LikeListOnCommentView.as_view(),
        name='like-list-on-comment'
    ),
]
