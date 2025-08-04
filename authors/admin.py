from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.hashers import make_password
from django import forms
from .models import Author, Follow, RemoteNode


@admin.register(Author)
class AuthorAdmin(UserAdmin):
    """Admin interface for Author model"""

    fieldsets = list(UserAdmin.fieldsets or []) + [
        ('Author Info', {
            'fields': ('serial', 'url', 'host', 'display_name', 'github',
                       'profile_image')
        }),
    ]
    add_fieldsets = list(UserAdmin.add_fieldsets or []) + [
        ('Author Info', {
            'fields': ('display_name', 'github', 'profile_image', 'host')
        }),
    ]

    list_display = ['username', 'display_name', 'url', 'host', 'is_active']
    search_fields = ['username', 'display_name', 'host']


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Admin interface for Follow model"""

    list_display = [
        'follower',
        'following',
        'status',
        'created_at',
        'updated_at']
    list_filter = ['status', 'created_at']
    search_fields = ['follower__username', 'follower__display_name',
                     'following__username', 'following__display_name']
    raw_id_fields = ['follower', 'following']

    # Group by status
    fieldsets = [
        ('Follow Relationship', {
            'fields': ['follower', 'following', 'status']
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse'],
        }),
    ]

    readonly_fields = ['created_at', 'updated_at']

    # Actions for bulk approval/rejection
    actions = ['approve_follows', 'reject_follows']

    @admin.action(description="Approve selected follow requests")
    def approve_follows(self, request, queryset):
        """Bulk approve follow requests"""
        updated = queryset.update(status=Follow.Status.ACCEPTED)
        self.message_user(request, f"{updated} follow requests approved.")

    @admin.action(description="Reject selected follow requests")
    def reject_follows(self, request, queryset):
        """Bulk reject follow requests"""
        updated = queryset.update(status=Follow.Status.REJECTED)
        self.message_user(request, f"{updated} follow requests rejected.")


class RemoteNodeAdminForm(forms.ModelForm):
    """Custom form for RemoteNode to handle password hashing."""
    outgoing_password = forms.CharField(
        widget=forms.PasswordInput(render_value=True), required=False,
        help_text="Set or change the password to connect TO the remote node. "
                  "Leave blank to keep the current password."
    )
    incoming_password = forms.CharField(
        widget=forms.PasswordInput(
            render_value=False), required=False, help_text=(
            "Set or change the password for the remote node to connect "
            "WITH US. "
            "Leave blank to keep the current password."))

    class Meta:
        model = RemoteNode
        fields = '__all__'
        widgets = {
            'outgoing_password': forms.PasswordInput(render_value=True),
            'incoming_password': forms.PasswordInput(render_value=True),
        }

    def save(self, commit=True):
        """Hash the incoming password before saving."""
        node = super().save(commit=False)
        password = self.cleaned_data.get("incoming_password")
        if password:
            node.incoming_password = make_password(password)
        if commit:
            node.save()
        return node


@admin.register(RemoteNode)
class RemoteNodeAdmin(admin.ModelAdmin):
    """Admin interface for RemoteNode model"""
    form = RemoteNodeAdminForm
    list_display = (
        'host',
        'outgoing_username',
        'incoming_username',
        'is_active')
    search_fields = ('host', 'outgoing_username', 'incoming_username')
    list_filter = ('is_active',)
    fieldsets = (
        ('Connection Properties', {
            'fields': ('host', 'is_active')
        }),
        ('Outgoing Connection (Us to Them)', {
            'description': (
                "Credentials we use to connect to the remote node's "
                "API."
            ),
            'fields': ('outgoing_username', 'outgoing_password')
        }),
        ('Incoming Connection (Them to Us)', {
            'description': (
                "Credentials the remote node uses to "
                "connect to our API."
            ),
            'fields': ('incoming_username', 'incoming_password')
        }),
    )

    def save_model(self, request, obj, form, change):
        """Hash password on save."""
        # The form's save method already handles hashing
        form.save()
