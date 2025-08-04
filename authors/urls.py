from django.urls import path
from . import views

urlpatterns = [
    # General list view first is fine
    path('authors/', views.AuthorListView.as_view(), name='author-list'),

    # --- All SPECIFIC author sub-paths must come BEFORE the general one ---
    # Followers API
    path(
        'authors/<uuid:serial>/followers/<path:foreign_author_fqid>/',
        views.FollowerDetailView.as_view(),
        name='follower-detail'
    ),
    path(
        'authors/<uuid:serial>/followers/',
        views.FollowersListView.as_view(),
        name='followers-list'
    ),
    # Friend API
    path(
        "authors/<uuid:serial>/friends/",
        views.FriendsListView.as_view(),
        name="friends-list",
    ),
    # Follow-requests view
    path(
        'authors/<path:serial_or_fqid>/follow-requests/',
        views.PendingFollowRequestsView.as_view(),
        name='follow-requests-list'
    ),

    path(
        'authors/<path:serial_or_fqid>/following/',
        views.FollowingListView.as_view(),
        name='following-list'
    ),

    # Commented API
    path(
        'authors/<path:serial_or_fqid>/commented/<uuid:comment_serial>/',
        views.AuthorCommentedDetailView.as_view(),
        name='author-commented-detail'
    ),
    path(
        'authors/<path:serial_or_fqid>/commented/',
        views.AuthorCommentedListView.as_view(),
        name='author-commented-list'
    ),
    path(
        'commented/<path:comment_fqid>/',
        views.CommentByFQIDView.as_view(),
        name='comment-by-fqid'
    ),

    # Liked API
    path(
        'authors/<path:serial_or_fqid>/liked/<uuid:like_serial>/',
        views.AuthorLikedDetailView.as_view(),
        name='author-liked-detail'
    ),
    path(
        'authors/<path:serial_or_fqid>/liked/',
        views.AuthorLikedListView.as_view(),
        name='author-liked-list'
    ),
    path(
        'liked/<path:like_fqid>/',
        views.LikeByFQIDView.as_view(),
        name='like-by-fqid'
    ),

    # Inbox API
    path(
        'authors/<uuid:author_serial>/inbox/',
        views.InboxView.as_view(),
        name='inbox'
    ),

    path(
        'authors/<path:serial_or_fqid>/',
        views.AuthorDetailView.as_view(),
        name='author-detail'),
]
