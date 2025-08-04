import os
from authors.models import Author
from django.shortcuts import render, redirect
from .forms import SignupForm, LoginForm
from django.contrib.auth import (
    login as auth_login,
    logout as django_logout,
)
from django.contrib.auth.decorators import login_required
from django.conf import settings
from uuid import uuid4


def register(request):
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.serial = uuid4()

            user.host = request.build_absolute_uri('/')
            user.url = f"{user.host.rstrip('/')}/api/authors/{user.serial}/"
            user.display_name = user.username

            if settings.SIGNUP_REQUIRES_APPROVAL:
                user.is_active = False
            else:
                user.is_active = True
            user.save()
            return redirect('login')
    else:
        form = SignupForm()

    return render(request, 'register.html', {'registerform': form})


def login(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            return redirect('ui')
        else:
            username = form.data.get('username')
            if username:
                user = Author.objects.filter(username=username).first()
                if user and not user.is_active:
                    form.errors.clear()
                    form.add_error(
                        None,
                        'Your account is pending administrator approval.'
                    )
    else:
        form = LoginForm()

    return render(request, 'login.html', {'loginform': form})


def logout(request):
    django_logout(request)
    return redirect('ui')


@login_required(login_url='login')
def ui_view(request):
    current_user_uuid = request.user.serial

    context = {
        'current_user': request.user,
        'current_user_uuid': current_user_uuid,
        'current_node_name': os.environ.get('NODE_NAME', 'default'),
    }
    return render(request, 'ui2.html', context)


@login_required(login_url='login')
def connect_view(request):
    current_user_uuid = request.user.serial

    context = {
        'current_user': request.user,
        'current_user_uuid': current_user_uuid,
        'current_node_name': os.environ.get('NODE_NAME', 'default'),
    }
    return render(request, 'connect.html', context)


def entry_detail(request, author_serial, entry_serial):
    from entries.models import Entry

    # Get the entry to check visibility
    try:
        entry = Entry.objects.get(
            serial=entry_serial,
            author__serial=author_serial,
            is_deleted=False
        )
    except Entry.DoesNotExist:
        return redirect('login')

    # Check permissions based on entry visibility
    if entry.visibility == 'FRIENDS':
        # FRIENDS entries require authentication and friendship
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user != entry.author and not request.user.is_friend_with(
                entry.author):
            return redirect('login')
    elif entry.visibility not in ['PUBLIC', 'UNLISTED']:
        # Any other visibility (including DELETED) requires being the author
        if not request.user.is_authenticated or request.user != entry.author:
            return redirect('login')

    current_user_uuid = (
        request.user.serial if request.user.is_authenticated else None
    )

    context = {
        'current_user': (
            request.user if request.user.is_authenticated else None
        ),
        'current_user_uuid': current_user_uuid,
        'current_entry_uuid': entry_serial,
        'current_entry_author_uuid': author_serial,
        'current_node_name': os.environ.get(
            'NODE_NAME',
            'default'),
    }
    return render(request, 'ui2.html', context)
