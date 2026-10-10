import uuid
from django.core.cache import cache
from django.db import models
from apps.stores.models import Store
from apps.authentication.models import User

AI_SETTINGS_CACHE_KEY = 'ai:provider_settings'

# Every provider here speaks the same OpenAI-compatible /chat/completions
# shape (Groq is itself just an OpenAI-compatible endpoint - see
# apps/ai/views.py) - so switching providers is just pointing the same
# request at a different base_url with a different key, not different
# request-building code. 'custom' lets an admin point at any other
# OpenAI-compatible host (OpenRouter, a self-hosted vLLM server, etc.)
# without a code change.
PROVIDER_GROQ = 'groq'
PROVIDER_OPENAI = 'openai'
PROVIDER_CUSTOM = 'custom'
PROVIDER_CHOICES = [
    (PROVIDER_GROQ, 'Groq'),
    (PROVIDER_OPENAI, 'OpenAI'),
    (PROVIDER_CUSTOM, 'Custom (OpenAI-compatible endpoint)'),
]

PROVIDER_DEFAULTS = {
    PROVIDER_GROQ: {
        'base_url': 'https://api.groq.com/openai/v1/chat/completions',
        'default_model': 'openai/gpt-oss-120b',
    },
    PROVIDER_OPENAI: {
        'base_url': 'https://api.openai.com/v1/chat/completions',
        'default_model': 'gpt-4o-mini',
    },
}


class AISettings(models.Model):
    """
    Singleton (always pk=1) holding which AI provider/model the AI
    Assistant (apps/ai/views.py) actually calls right now - the live,
    admin-editable version of what used to be pinned to the GROQ_API_KEY /
    GROQ_MODEL env vars alone. Same singleton + read-through-cache pattern
    as apps/billing/models.py's TrialSettings/PricingSettings: edit this
    from Django Admin (AI > AI provider & model) and it takes effect on the
    very next chat request, no redeploy.

    API keys are still read from environment variables per provider
    (GROQ_API_KEY / OPENAI_API_KEY) by default - never stored in the DB in
    plaintext - unless `api_key_override` is explicitly set here, which is
    useful for a quick provider switch without a deploy/env-var change
    (e.g. testing a different Groq key). Leave it blank to use the env var
    for whichever provider is selected.
    """
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_GROQ)
    model_name = models.CharField(
        max_length=200, blank=True,
        help_text='e.g. openai/gpt-oss-120b (Groq), gpt-4o-mini (OpenAI). '
                   'Leave blank to use the provider\'s default model.',
    )
    custom_base_url = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Only used when provider = "Custom". Full chat-completions URL, '
                   'e.g. https://openrouter.ai/api/v1/chat/completions',
    )
    api_key_override = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Optional. Leave blank to use GROQ_API_KEY / OPENAI_API_KEY from the '
                   'environment for the selected provider. Only set this for a quick test '
                   'without changing environment variables - prefer the env var in production.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_settings'
        verbose_name = 'AI settings'
        verbose_name_plural = 'AI settings'

    def __str__(self):
        return f'{self.get_provider_display()} \u2014 {self.model_name or "(default model)"}'

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton - there is only ever one row
        super().save(*args, **kwargs)
        cache.delete(AI_SETTINGS_CACHE_KEY)


def get_ai_config():
    """
    The {provider, model, base_url, api_key} to actually use for the NEXT
    AI Assistant request. Everywhere that used to read settings.GROQ_MODEL
    / settings.GROQ_API_KEY directly for the live call should go through
    this instead - same cache-with-immediate-invalidation pattern as
    apps.billing.models.get_trial_period_days().

    Falls back to the original env-var-only Groq behavior when no
    AISettings row exists yet, so nothing breaks before an admin first
    visits the AI provider & model page.
    """
    from django.conf import settings

    cached = cache.get(AI_SETTINGS_CACHE_KEY)
    if cached is None:
        obj, _created = AISettings.objects.get_or_create(
            pk=1, defaults={'provider': PROVIDER_GROQ, 'model_name': settings.GROQ_MODEL},
        )
        cached = {
            'provider': obj.provider,
            'model_name': obj.model_name,
            'custom_base_url': obj.custom_base_url,
            'api_key_override': obj.api_key_override,
        }
        cache.set(AI_SETTINGS_CACHE_KEY, cached, 300)

    provider = cached['provider']
    if provider == PROVIDER_CUSTOM:
        base_url = cached['custom_base_url']
    else:
        base_url = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS[PROVIDER_GROQ])['base_url']

    model = cached['model_name'] or PROVIDER_DEFAULTS.get(provider, {}).get('default_model') or settings.GROQ_MODEL

    if cached['api_key_override']:
        api_key = cached['api_key_override']
    elif provider == PROVIDER_OPENAI:
        api_key = getattr(settings, 'OPENAI_API_KEY', '')
    elif provider == PROVIDER_CUSTOM:
        # No sensible env-var fallback exists for an arbitrary
        # OpenAI-compatible endpoint - GROQ_API_KEY would silently send the
        # wrong bearer token to someone else's API and fail with a
        # confusing 401 instead of the clear "AI service not configured"
        # message the empty-string case below produces. A custom provider
        # MUST use api_key_override.
        api_key = ''
    else:
        api_key = settings.GROQ_API_KEY

    return {'provider': provider, 'model': model, 'base_url': base_url, 'api_key': api_key}


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
    # Soft delete: "Clear chat" from the user's side only sets this. The
    # message stays in the database so admins can still read it (support,
    # abuse review); every USER-facing query filters deleted_at__isnull=True.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'ai_chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['store', 'user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"
