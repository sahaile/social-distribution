import os
import django


def pytest_configure():
    """Configure Django settings for pytest"""
    os.environ.setdefault(
        'DJANGO_SETTINGS_MODULE',
        'socialdistribution.settings')
    django.setup()
