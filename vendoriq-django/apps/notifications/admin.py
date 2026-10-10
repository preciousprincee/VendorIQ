from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.authentication.models import User
from .models import Announcement, Notification


@admin.action(description='Withdraw selected announcements (hide from everyone)')
def withdraw(modeladmin, request, queryset):
    modeladmin.message_user(request, f'Withdrew {queryset.update(is_active=False)} announcement(s).')


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin):
    """
    "Send a notification to all users": Add announcement, fill in the title
    and message, Save. It appears in every user's notification bell (with an
    unread badge) straight away - no email/SMS is sent. Edit the text or
    untick "Is active" later to change or withdraw it.
    """
    list_display = ['title', 'is_active', 'created_at', 'expires_at', 'created_by', 'reach']
    list_filter = ['is_active']
    search_fields = ['title', 'message']
    readonly_fields = ['created_by', 'created_at']
    fields = ['title', 'message', 'link', 'is_active', 'expires_at', 'created_by', 'created_at']
    actions = [withdraw]

    @admin.display(description='Reaches')
    def reach(self, obj):
        return f'All {User.objects.filter(is_active=True).count()} active users' if obj.is_active else 'Withdrawn'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Notification)
class NotificationAdmin(ModelAdmin):
    """Read-only log of the per-user reminders the system generated (subscription ending/expired)."""
    list_display = ['created_at', 'user', 'kind', 'title']
    list_filter = ['kind']
    search_fields = ['user__email', 'title', 'message']
    date_hierarchy = 'created_at'
    readonly_fields = ['user', 'kind', 'severity', 'title', 'message', 'link', 'dedupe_key', 'created_at']

    def has_add_permission(self, request):
        return False
