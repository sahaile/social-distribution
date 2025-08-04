from django.contrib import admin
from .models import Entry, Comment, Like


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'visibility', 'published', 'is_deleted')
    list_filter = ('visibility', 'is_deleted', 'content_type')
    search_fields = ('title', 'description', 'content', 'author__username')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('entry', 'author', 'published')
    search_fields = ('comment', 'author__username', 'entry__title')


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('content_object', 'author', 'published')
    search_fields = ('author__username',)
