from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Follow
from drf_spectacular.utils import extend_schema_field

Author = get_user_model()


class AuthorSerializer(serializers.ModelSerializer):
    """Serializer for the Author model (user accounts)"""
    type = serializers.CharField(default='author', read_only=True)
    id = serializers.SerializerMethodField(
        help_text="The FQID of the author. Example: "
                  "http://host/api/authors/{author_id}"
    )
    host = serializers.URLField(
        read_only=True,
        help_text=(
            "The host node of the author. "
            "Example: 'http://127.0.0.1:8000/'"
        )
    )
    displayName = serializers.CharField(
        source='display_name',
        help_text="The author's display name. Example: 'John Doe'"
    )
    github = serializers.URLField(
        help_text=(
            "The URL to the author's GitHub profile. "
            "Example: 'https://github.com/johndoe'"
        ),
        allow_blank=True
    )
    profileImage = serializers.URLField(
        source='profile_image',
        help_text=(
            "The URL to the author's profile image. "
            "Example: 'https://example.com/image.jpg'"
        ),
        allow_blank=True
    )
    web = serializers.SerializerMethodField(
        help_text="The web URL of the author's profile. Example: "
                  "http://host/authors/{author_id}"
    )
    followers_count = serializers.SerializerMethodField(
        help_text="The number of followers this author has. Example: 10"
    )
    following_count = serializers.SerializerMethodField(
        help_text="The number of authors this author is following. "
                  "Example: 12"
    )
    friends_count = serializers.SerializerMethodField(
        help_text="The number of mutual friends this author has. Example: 5"
    )

    class Meta:
        model = Author
        fields = [
            'type', 'id', 'host', 'displayName', 'github', 'profileImage',
            'web', 'followers_count', 'following_count', "friends_count",]

    @extend_schema_field(serializers.URLField())
    def get_id(self, obj):
        """Return FQID for the author"""
        request = self.context.get('request')
        if not request:
            raise ValueError("A 'request' must be provided in the context.")

        # For proxy authors (remote authors), use their stored URL
        # instead of building it from the current request
        if self._is_proxy_author(obj, request):
            return obj.url

        return obj.get_api_url(request=request)

    @extend_schema_field(serializers.URLField())
    def get_web(self, obj):
        """Return web profile URL"""
        request = self.context.get('request')

        # For proxy authors (remote authors), use local proxy URL
        if self._is_proxy_author(obj, request):
            return request.build_absolute_uri(f"/authors/{obj.serial}/")

        return obj.get_web_url(request=request)

    def _is_proxy_author(self, author, request):
        """Check if an author is a proxy (remote) author"""
        if not author.host:
            return False

        current_host = f"{request.scheme}://{request.get_host()}/"
        author_host = author.host.rstrip('/') + '/'

        # If hosts differ, this is a proxy author
        return author_host != current_host

    @extend_schema_field(serializers.IntegerField())
    def get_followers_count(self, obj):
        """Return the number of accepted followers"""
        return obj.get_followers().count()

    @extend_schema_field(serializers.IntegerField())
    def get_following_count(self, obj):
        """Return the number of accepted authors this user is following"""
        return obj.get_following().count()

    @extend_schema_field(serializers.IntegerField())
    def get_friends_count(self, obj):
        """Return the number of mutual friends"""
        return obj.get_friends().count()


class FollowSerializer(serializers.ModelSerializer):
    """Serializer for Follow request objects"""

    type = serializers.CharField(
        default='follow',
        read_only=True,
        help_text=(
            "The type of the object. Always 'follow'."
        )
    )
    summary = serializers.SerializerMethodField(
        help_text=(
            "A human-readable summary of the follow request. "
            "Example: 'John Doe wants to follow Jane Smith'"
        )
    )
    actor = AuthorSerializer(
        source='follower',
        read_only=True,
        help_text=(
            "The author who is initiating the follow action."
        )
    )
    object = AuthorSerializer(
        source='following',
        read_only=True,
        help_text="The author who is being followed."
    )

    class Meta:
        model = Follow
        fields = ['type', 'summary', 'actor', 'object']

    def get_summary(self, obj):
        """Return human-readable summary of the follow request"""
        follower_name = obj.follower.display_name or obj.follower.username
        following_name = obj.following.display_name or obj.following.username
        return f"{follower_name} wants to follow {following_name}"


class FollowersListSerializer(serializers.Serializer):
    """Serializer for the followers list response"""

    type = serializers.CharField(
        default='followers',
        read_only=True,
        help_text="The type of the object. Always 'followers'."
    )
    followers = AuthorSerializer(
        many=True,
        read_only=True,
        help_text="A list of author objects who are following the user."
    )


class FriendsListSerializer(serializers.Serializer):
    """Serializer for the friends list response"""

    type = serializers.CharField(
        default="friends",
        read_only=True,
        help_text="The type of the object. Always 'friends'.",
    )
    friends = AuthorSerializer(
        many=True,
        read_only=True,
        help_text="A list of mutual friends with the user.",
    )


class FollowingListSerializer(serializers.Serializer):
    """Serializer for the following list response"""
    type = serializers.CharField(
        default='following',
        read_only=True,
        help_text="The type of the object. Always 'following'."
    )
    following = AuthorSerializer(
        many=True,
        read_only=True,
        help_text="A list of author objects that the user is following."
    )


class AuthorsListSerializer(serializers.Serializer):
    """Serializer for the authors list response wrapper"""

    type = serializers.CharField(
        default='authors',
        read_only=True,
        help_text="The type of the object. Always 'authors'."
    )
    authors = AuthorSerializer(
        many=True,
        read_only=True,
        help_text="A list of author objects on the node."
    )


class RemoteAuthorValidationSerializer(serializers.Serializer):
    """
    A serializer to validate the format of author data received from a
    remote server before creating a local proxy object. It does not save
    anything to the database directly.
    """
    type = serializers.CharField(required=True)
    id = serializers.URLField(required=True)
    host = serializers.URLField(required=True)
    displayName = serializers.CharField(required=True)
    github = serializers.URLField(required=False, allow_blank=True)
    profileImage = serializers.URLField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        raise NotImplementedError(
            "This serializer is for validation only.")

    def update(self, instance, validated_data):
        raise NotImplementedError(
            "This serializer is for validation only.")
