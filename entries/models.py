import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType

Author = get_user_model()

VISIBILITY_CHOICES = [
    ('PUBLIC', 'Public'),
    ('FRIENDS', 'Friends only'),
    ('UNLISTED', 'Unlisted'),
    ('DELETED', 'Deleted'),
]

CONTENT_TYPE_CHOICES = [
    ('text/plain', 'Plain text'),
    ('text/markdown', 'Markdown'),
    ('application/base64', 'Base64'),
    ('image/png;base64', 'PNG image'),
    ('image/jpeg;base64', 'JPEG image'),
]


class Entry(models.Model):
    """An author's entry in the blog."""

    # FQID of the entry.
    url: models.URLField = models.URLField(
        max_length=512,
        primary_key=True,
        help_text="The fully qualified ID of this entry."
    )
    # Local identifier for URL construction
    serial: models.UUIDField = models.UUIDField(
        default=uuid.uuid4, editable=False)

    # Identification
    github_event_id: models.CharField = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="The unique ID of the GitHub event, "
        "if this entry was imported.")
    # Content
    title: models.CharField = models.CharField(max_length=200)
    description: models.TextField = models.TextField(blank=True)
    content: models.TextField = models.TextField()
    content_type: models.CharField = models.CharField(
        max_length=50, choices=CONTENT_TYPE_CHOICES)

    # Relationships
    author: models.ForeignKey = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name='entries',
        to_field='url'
    )

    # Metadata
    published: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated: models.DateTimeField = models.DateTimeField(auto_now=True)
    visibility: models.CharField = models.CharField(
        max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC')
    is_deleted: models.BooleanField = models.BooleanField(default=False)

    likes = GenericRelation('Like', related_query_name='entry')

    def save(self, *args, **kwargs):
        """Automatically generate the URL field if not set."""
        if not self.url:
            self.url = self.get_api_url()
        super().save(*args, **kwargs)

    def get_api_url(self):
        """Return the API URL for this entry"""
        return (f"{self.author.host.rstrip('/')}/api/authors/"
                f"{self.author.serial}/entries/{self.serial}")

    def get_web_url(self):
        """Return the web profile URL for this entry."""
        return (f"{self.author.host.rstrip('/')}/authors/"
                f"{self.author.serial}/entries/{self.serial}")


class Comment(models.Model):
    """A comment on an entry."""

    # FQID of the comment
    url: models.URLField = models.URLField(
        max_length=512,
        primary_key=True,
        help_text="The fully qualified ID of this comment."
    )
    # Local identifier for URL construction
    serial: models.UUIDField = models.UUIDField(
        default=uuid.uuid4, editable=False)

    # Relationships
    author: models.ForeignKey = models.ForeignKey(
        Author, on_delete=models.CASCADE, to_field='url')
    entry: models.ForeignKey = models.ForeignKey(
        Entry, on_delete=models.CASCADE, related_name='comments')

    # Content
    comment: models.TextField = models.TextField()
    content_type: models.CharField = models.CharField(
        max_length=50, default='text/plain')

    # Metadata
    published: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    likes = GenericRelation('Like', related_query_name='comment')

    def save(self, *args, **kwargs):
        """Automatically generate the URL field if not set."""
        if not self.url:
            self.url = self.get_api_url()
        super().save(*args, **kwargs)

    def get_api_url(self):
        """Return the FQID for this comment."""
        return (f"{self.author.host.rstrip('/')}/api/authors/"
                f"{self.author.serial}/commented/{self.serial}")


class Like(models.Model):
    """A like on an entry or comment."""

    # FQID of the like
    url: models.URLField = models.URLField(
        max_length=512,
        primary_key=True,
        help_text="The fully qualified ID of this like."
    )
    # Local identifier for URL construction
    serial: models.UUIDField = models.UUIDField(
        default=uuid.uuid4, editable=False)

    # Relationships
    author: models.ForeignKey = models.ForeignKey(
        Author, on_delete=models.CASCADE, to_field='url')

    # Generic relation to an object that can be liked (Entry or Comment)
    content_type: models.ForeignKey = models.ForeignKey(
        ContentType, on_delete=models.CASCADE)
    object_id: models.CharField = models.CharField(max_length=512)
    content_object: GenericForeignKey = GenericForeignKey(
        'content_type', 'object_id')

    # Metadata
    published: models.DateTimeField = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        """Automatically generate the URL field if not set."""
        if not self.url:
            self.url = self.get_api_url()
        super().save(*args, **kwargs)

    def get_api_url(self):
        """Return the FQID for this like."""
        return (f"{self.author.host.rstrip('/')}/api/authors/"
                f"{self.author.serial}/liked/{self.serial}")
