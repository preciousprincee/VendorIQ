from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import ChatMessage


@admin.register(ChatMessage)
class ChatMessageAdmin(ModelAdmin):
    list_display = ['store', 'user', 'role', 'created_at']
    list_filter = ['role', 'store']
    search_fields = ['content', 'user__email']
