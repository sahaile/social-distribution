"""
URL configuration for socialdistribution project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
)
from authors.views import FollowersPageView, FollowingPageView, FriendsPageView
from authors.views import AuthorProfilePageView, AuthorProfilePageEditView
from . import views


urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Authentication
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),

    # API
    # API Schema:
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # UI:
    path(
        'api/schema/swagger-ui/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui'),
    path(
        'api/schema/redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc'),
    path('api/', include('entries.urls')),
    path('api/', include('authors.urls')),

    # Frontend
    path('',
         views.ui_view,
         name='ui'
         ),
    path('connect/',
         views.connect_view,
         name='connect'
         ),
    path(
        'authors/<uuid:serial>/',
        AuthorProfilePageView.as_view(),
        name='web-author-profile'
    ),
    path(
        'authors/<uuid:serial>/edit/',
        AuthorProfilePageEditView.as_view(),
        name='web-author-profile-edit'
    ),
    path(
        'authors/<uuid:serial>/followers/',
        FollowersPageView.as_view(),
        name='web-followers-list'
    ),
    path(
        'authors/<uuid:serial>/following/',
        FollowingPageView.as_view(),
        name='web-following-list'
    ),
    path(
        'authors/<uuid:serial>/followers/',
        FollowersPageView.as_view(),
        name='web-followers-list'
    ),
    path(
        'authors/<uuid:serial>/following/',
        FollowingPageView.as_view(),
        name='web-following-list'
    ),
    path('authors/<uuid:serial>/friends/',
         FriendsPageView.as_view(),
         name='web-friends-list'),
    path(
        'authors/<uuid:author_serial>/entries/<uuid:entry_serial>/',
        views.entry_detail,
        name='entry-detail'
    ),
]
