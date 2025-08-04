from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema_field
from .models import Entry, Comment, Like
from authors.serializers import AuthorSerializer


@extend_schema_field(serializers.URLField())
def get_fqid_url(obj):
    """Generic helper to return the FQID of an object."""
    if hasattr(obj, 'get_api_url'):
        return obj.get_api_url()
    return None


class LikeSerializer(serializers.ModelSerializer):
    """Serializer for Like API objects"""
    type = serializers.CharField(default='like', read_only=True)
    author = AuthorSerializer(read_only=True)
    object = serializers.SerializerMethodField(
        help_text="The FQID of the liked object (entry or comment)."
    )
    id = serializers.SerializerMethodField(
        help_text="The FQID of the like object itself."
    )

    class Meta:
        model = Like
        fields = ['type', 'author', 'object', 'published', 'id']
        extra_kwargs = {
            'published': {
                'help_text': "The date and time the like was created."
            }
        }

    @extend_schema_field(serializers.URLField())
    def get_id(self, obj):
        """Return the FQID of the like object"""
        return obj.get_api_url()

    @extend_schema_field(serializers.URLField())
    def get_object(self, obj):
        """Return the FQID of the liked object (entry or comment)"""
        if hasattr(obj.content_object, 'get_api_url'):
            return obj.content_object.get_api_url()
        return None


class CommentSerializer(serializers.ModelSerializer):
    """Serializer for Comment API objects"""
    type = serializers.CharField(default='comment', read_only=True)
    author = AuthorSerializer(read_only=True)
    id = serializers.SerializerMethodField(
        help_text="The FQID of the comment object."
    )
    web = serializers.SerializerMethodField(
        help_text="The web URL of the parent entry."
    )
    entry = serializers.SerializerMethodField(
        help_text="The FQID of the parent entry."
    )
    likes = serializers.SerializerMethodField(
        help_text="A summary of likes on this comment."
    )
    contentType = serializers.CharField(
        source='content_type',
        help_text="The content type of the comment, e.g., 'text/plain'."
    )

    class Meta:
        model = Comment
        fields = [
            'type', 'author', 'comment', 'contentType',
            'published', 'id', 'web', 'entry', 'likes', 'serial'
        ]
        extra_kwargs = {
            'comment': {
                'help_text': "The content of the comment."
            },
            'published': {
                'help_text': "The date and time the comment was created."
            },
            'serial': {
                'help_text': "The local UUID of the comment."
            },
        }

    @extend_schema_field(serializers.URLField())
    def get_id(self, obj):
        """Return the FQID of the comment object"""
        return obj.get_api_url()

    @extend_schema_field(serializers.URLField())
    def get_web(self, obj):
        """Return the web URL of the parent entry"""
        return obj.entry.get_web_url()

    @extend_schema_field(serializers.URLField())
    def get_entry(self, obj):
        """Return the FQID of the parent entry"""
        return obj.entry.get_api_url()

    @extend_schema_field(serializers.DictField())
    def get_likes(self, obj):
        """
        Return a paginated-like summary of the first 5 likes for the comment.
        """
        content_type = ContentType.objects.get_for_model(obj)
        likes_queryset = Like.objects.filter(
            content_type=content_type, object_id=obj.url
        ).order_by('-published')

        count = likes_queryset.count()
        first_5_likes = likes_queryset[:5]
        like_serializer = LikeSerializer(
            first_5_likes, many=True, context=self.context)

        return {
            "type": "likes",
            "id": f"{obj.get_api_url()}/likes",
            "page_number": 1,
            "size": 5,
            "count": count,
            "src": like_serializer.data,
        }


class EntrySerializer(serializers.ModelSerializer):
    """Serializer for Entry API objects"""
    type = serializers.CharField(default='entry', read_only=True)
    id = serializers.SerializerMethodField(
        help_text="The FQID of the entry."
    )
    web = serializers.SerializerMethodField(
        help_text="The web URL of the entry."
    )
    author = AuthorSerializer(read_only=True)
    comments = serializers.SerializerMethodField(
        help_text="A summary of the first 5 comments on this entry."
    )
    likes = serializers.SerializerMethodField(
        help_text="A summary of the first 5 likes on this entry."
    )
    contentType = serializers.CharField(
        source='content_type',
        help_text="The MIME type of the content."
    )

    class Meta:
        model = Entry
        fields = [
            'type', 'title', 'id', 'web', 'description', 'contentType',
            'content', 'author', 'comments', 'likes', 'published',
            'visibility'
        ]
        extra_kwargs = {
            'title': {
                'help_text': "The title of the entry."
            },
            'description': {
                'help_text': "A brief description of the entry."
            },
            'content': {
                'help_text': "The main content of the entry. For images, "
                             "this is a base64 encoded string."
            },
            'published': {
                'help_text': "The date and time the entry was published."
            },
            'visibility': {
                'help_text': "Controls who can see the entry (PUBLIC, "
                             "FRIENDS, UNLISTED)."
            },
        }

    def validate(self, data):
        data = super().validate(data)

        match data["content_type"]:
            case "text/markdown" | "text/plain":
                return data
            case ("image/png;base64"
                  ) if data["content"].startswith("iVBORw0KGgo"):
                return data
            case "image/jpeg;base64" if data["content"].startswith("/9j/"):
                return data
            case ("application/base64"):
                # TODO: Check if valid image type.
                return data
            case _:
                raise ValidationError(
                    "Unsupported content with specified contentType.")

    @extend_schema_field(serializers.URLField())
    def get_id(self, obj):
        return obj.get_api_url()

    @extend_schema_field(serializers.URLField())
    def get_web(self, obj):
        return obj.get_web_url()

    @extend_schema_field(serializers.DictField())
    def get_comments(self, obj):
        """
        Return a paginated-like summary of the first 5 comments for the entry.
        """
        comments_queryset = obj.comments.all().order_by('-published')
        count = comments_queryset.count()
        first_5_comments = comments_queryset[:5]
        comment_serializer = CommentSerializer(
            first_5_comments, many=True, context=self.context)

        return {
            "type": "comments",
            "id": f"{obj.get_api_url()}/comments",
            "web": f"{obj.get_web_url()}/comments",
            "page_number": 1,
            "size": 5,
            "count": count,
            "src": comment_serializer.data,
        }

    @extend_schema_field(serializers.DictField())
    def get_likes(self, obj):
        """
        Return a paginated-like summary of the first 5 likes for the entry.
        """
        content_type = ContentType.objects.get_for_model(obj)
        likes_queryset = Like.objects.filter(
            content_type=content_type, object_id=obj.serial
        ).order_by('-published')

        count = likes_queryset.count()
        first_5_likes = likes_queryset[:5]
        like_serializer = LikeSerializer(
            first_5_likes, many=True, context=self.context)

        return {
            "type": "likes",
            "id": f"{obj.get_api_url()}/likes",
            "web": f"{obj.get_web_url()}/likes",
            "page_number": 1,
            "size": 5,
            "count": count,
            "src": like_serializer.data,
        }


class PaginatedCommentSerializer(serializers.Serializer):
    """Serializer for a paginated list of comments"""
    type = serializers.CharField(default='comments', read_only=True)
    page_number = serializers.IntegerField(
        help_text="The current page number.")
    size = serializers.IntegerField(help_text="The number of items per page.")
    count = serializers.IntegerField(help_text="The total number of items.")
    src = CommentSerializer(
        many=True,
        read_only=True,
        help_text="The list of comment objects for the current page."
    )


class PaginatedLikeSerializer(serializers.Serializer):
    """Serializer for a paginated list of likes"""
    type = serializers.CharField(default='likes', read_only=True)
    page_number = serializers.IntegerField(
        help_text="The current page number.")
    size = serializers.IntegerField(help_text="The number of items per page.")
    count = serializers.IntegerField(help_text="The total number of items.")
    src = LikeSerializer(
        many=True,
        read_only=True,
        help_text="The list of like objects for the current page."
    )


class EntryListSerializer(serializers.Serializer):
    """Serializer for the paginated list of entries response wrapper"""
    type = serializers.CharField(default='entries')
    page_number = serializers.IntegerField(
        help_text="The current page number.")
    size = serializers.IntegerField(help_text="The number of items per page.")
    count = serializers.IntegerField(help_text="The total number of entries.")
    src = EntrySerializer(
        many=True,
        help_text="The list of entry objects for the current page."
    )


class CommentListResponseSerializer(serializers.Serializer):
    """Serializer for the response of a comment list endpoint"""
    type = serializers.CharField(default='comments')
    page_number = serializers.IntegerField(
        help_text="The current page number.")
    size = serializers.IntegerField(help_text="The number of items per page.")
    count = serializers.IntegerField(help_text="The total number of comments.")
    id = serializers.URLField(help_text="The FQID of the comments endpoint.")
    web = serializers.URLField(help_text="The web URL for these comments.")
    src = CommentSerializer(
        many=True,
        help_text="The list of comment objects for the current page."
    )


class LikeListResponseSerializer(serializers.Serializer):
    """Serializer for the response of a like list endpoint"""
    type = serializers.CharField(default='likes')
    page_number = serializers.IntegerField(
        help_text="The current page number.")
    size = serializers.IntegerField(help_text="The number of items per page.")
    count = serializers.IntegerField(help_text="The total number of likes.")
    id = serializers.URLField(help_text="The FQID of the likes endpoint.")
    web = serializers.URLField(help_text="The web URL for these likes.")
    src = LikeSerializer(
        many=True,
        help_text="The list of like objects for the current page."
    )


class ImageSerializer(serializers.Serializer):
    pass
