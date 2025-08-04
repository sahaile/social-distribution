from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class RemoteNode(models.Model):
    """
    Represents a remote node in the distributed social network.
    Stores the necessary information to communicate with a remote server,
    and the credentials for remote nodes to communicate with us.
    """
    host: models.URLField = models.URLField(
        unique=True,
        help_text=(
            "The base URL of the remote node "
            "(e.g., 'https://another-node.herokuapp.com/')"
        )
    )

    # Credentials for US to connect to THEM (outgoing)
    outgoing_username: models.CharField = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "The username for HTTP Basic Auth to connect "
            "TO the remote node."
        )
    )
    outgoing_password: models.CharField = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "The password for HTTP Basic Auth to connect "
            "TO the remote node."
        )
    )

    # Credentials for THEM to connect to US (incoming)
    incoming_username: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "The username a remote node uses to authenticate "
            "with US."
        )
    )
    incoming_password: models.CharField = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text=(
            "The hashed password a remote node uses to authenticate "
            "with US."
        )
    )

    is_active: models.BooleanField = models.BooleanField(
        default=True,
        help_text=(
            "Designates whether this remote node connection is active."
        )
    )

    def __str__(self):
        return self.host


class Author(AbstractUser):
    """User model representing an author"""

    # FQID of the author
    # E.g., "http://127.0.0.1:8000/api/authors/some-uuid/"
    url: models.CharField = models.URLField(
        max_length=512,
        unique=True,
        help_text="The fully qualified ID of this author."
    )

    # Use UUID for serial. This is a local identifier to help build the URL.
    serial: models.UUIDField = models.UUIDField(
        default=uuid.uuid4, unique=True, db_index=True)

    # Fields
    host: models.URLField = models.URLField(
        max_length=500,
        help_text="URL of this author's node")
    display_name: models.CharField = models.CharField(
        max_length=150, blank=True)
    github: models.URLField = models.URLField(max_length=500, blank=True)
    profile_image: models.URLField = models.URLField(
        max_length=500, blank=True)

    def get_api_url(self, request=None):
        """
        Return the FQID for this author. Uses the request to build the
        absolute URI if provided.
        """
        if request:
            return request.build_absolute_uri(
                f"/api/authors/{self.serial}/"
            )
        # Ensure host has a trailing slash
        # Remove any trailing 'api/' to avoid invalid URLs.
        host = self.host.rstrip('api/').rstrip('/') + '/'
        return f"{host}api/authors/{self.serial}/"

    def get_web_url(self, request=None):
        """
        Return the web profile URL. Uses the request to build the
        absolute URI if provided.
        """
        if request:
            return request.build_absolute_uri(
                f"/authors/{self.serial}/"
            )
        return f"{self.host}authors/{self.serial}/"

    def get_followers(self):
        """Get all authors who are following this author
        (accepted follows only)"""
        return Author.objects.filter(
            following_relationships__following=self,
            following_relationships__status=Follow.Status.ACCEPTED
        )

    def get_following(self):
        """Get all authors this author is following (accepted follows only)"""
        return Author.objects.filter(
            follower_relationships__follower=self,
            follower_relationships__status=Follow.Status.ACCEPTED
        )

    def get_friends(self):
        """Get all authors who are mutual friends (both follow each other)"""
        # Find authors where both follow relationships exist and are accepted
        following_ids = self.get_following().values_list('serial', flat=True)
        followers = self.get_followers()
        return followers.filter(serial__in=following_ids)

    def is_following(self, other_author):
        """Check if this author is following another author
        (accepted follow only)"""
        return Follow.objects.filter(
            follower=self,
            following=other_author,
            status=Follow.Status.ACCEPTED
        ).exists()

    def is_friend_with(self, other_author):
        """Check if this author is friends with another author
        (mutual accepted follows)"""
        return (self.is_following(other_author) and
                other_author.is_following(self))

    def send_follow_request(self, target_author):
        """Send a follow request to another author"""
        if self == target_author:
            raise ValueError("Cannot follow yourself")

        follow, created = Follow.objects.get_or_create(
            follower=self,
            following=target_author,
            defaults={'status': Follow.Status.PENDING}
        )

        if not created:
            if follow.status in [
                    Follow.Status.PENDING,
                    Follow.Status.ACCEPTED]:
                raise ValueError(
                    f"Follow request already exists and is {
                        follow.status.lower()}.")
            elif follow.status == Follow.Status.REJECTED:
                # If the request was rejected, allow re-sending it.
                follow.status = Follow.Status.PENDING
                follow.save()

        return follow

    def get_pending_follow_requests(self):
        """Get all pending follow requests for this author to approve/deny"""
        return Follow.objects.filter(
            following=self,
            status=Follow.Status.PENDING
        ).order_by('-created_at')

    def save(self, *args, **kwargs):
        """Auto-populate url field if not set"""
        if not self.url and self.host:
            # Use get_api_url() to generate the FQID
            # Since we don't have a request, we'll build it manually
            host = self.host.rstrip('/') + '/'
            self.url = f"{host}api/authors/{self.serial}/"
        super().save(*args, **kwargs)


class Follow(models.Model):
    """Represents a follow relationship between two authors"""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'

    # Who is doing the following
    follower: models.ForeignKey = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name='following_relationships',
        to_field='url'
    )

    # Who is being followed
    following: models.ForeignKey = models.ForeignKey(
        Author,
        on_delete=models.CASCADE,
        related_name='follower_relationships',
        to_field='url'
    )

    # Status of the follow request
    status: models.CharField = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        # Ensure a user can only follow another user once
        unique_together = ('follower', 'following')
        indexes = [
            models.Index(fields=['follower', 'status']),
            models.Index(fields=['following', 'status']),
        ]

    def __str__(self):
        return f"{
            self.follower.username} -> {
            self.following.username} ({
            self.status})"

    def approve(self):
        """Approve this follow request"""
        self.status = self.Status.ACCEPTED
        self.save()

    def reject(self):
        """Reject this follow request"""
        self.status = self.Status.REJECTED
        self.save()

    def is_pending(self):
        """Check if this follow request is pending"""
        return self.status == self.Status.PENDING

    def is_accepted(self):
        """Check if this follow request is accepted"""
        return self.status == self.Status.ACCEPTED

    def is_rejected(self):
        """Check if this follow request is rejected"""
        return self.status == self.Status.REJECTED

    def clean(self):
        """Validate that a user cannot follow themselves"""
        from django.core.exceptions import ValidationError
        if self.follower == self.following:
            raise ValidationError("A user cannot follow themselves.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
