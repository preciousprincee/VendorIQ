import uuid
from django.db import models
from apps.stores.models import Store
from apps.authentication.models import User


class ChatMessage(models.Model):
    """
    Persists AI assistant conversations per store+user so the chat survives a
    page refresh/new session, and can be explicitly cleared by the user.
    """

    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='chat_messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['store', 'user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"
