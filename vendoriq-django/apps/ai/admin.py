from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from unfold.admin import ModelAdmin
from .models import ChatMessage, AISettings


class AISettingsAdminForm(forms.ModelForm):
    # Plain CharField (Django's default) renders `value="<current secret>"`
    # straight into the HTML input on every page load - meaning the real
    # key sits in plaintext in the page source/view-source every single
    # time anyone with admin access opens this page, not just when it's
    # first typed. PasswordInput(render_value=False) stops it being echoed
    # back at all; clean_api_key_override() below then treats a blank
    # submit as "leave the existing key alone" (since the field always
    # LOOKS blank now) rather than accidentally wiping a real key just
    # because the admin didn't retype it while changing the model/provider.
    api_key_override = forms.CharField(
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text='Optional. Leave blank to use GROQ_API_KEY / OPENAI_API_KEY from the '
                   'environment for the selected provider. Only set this for a quick test '
                   'without changing environment variables - prefer the env var in production. '
                   'Always shows blank when reopening this page (even if a key is already set) '
                   'so it is never displayed in plaintext - leave it blank on save to keep the '
                   'current key, or type a new one to replace it.',
    )

    class Meta:
        model = AISettings
        fields = '__all__'

    def clean_api_key_override(self):
        return self.cleaned_data.get('api_key_override') or self.instance.api_key_override


@admin.register(ChatMessage)
class ChatMessageAdmin(ModelAdmin):
    """
    The raw, message-by-message table. For reading someone's actual
    conversation use AI > AI usage & conversations instead (one user at a
    time, rendered as a chat) - this list is only useful for searching
    across every message at once.
    """
    list_display = ['created_at', 'user', 'store', 'role', 'preview', 'deleted_by_user']
    list_filter = ['role', 'store', ('deleted_at', admin.EmptyFieldListFilter)]
    search_fields = ['content', 'user__email', 'user__name']
    date_hierarchy = 'created_at'
    readonly_fields = ['store', 'user', 'role', 'content', 'created_at', 'deleted_at']

    @admin.display(description='Message')
    def preview(self, obj):
        text = ' '.join((obj.content or '').split())
        return text if len(text) <= 90 else text[:87] + '...'

    @admin.display(description='Deleted by user', boolean=True)
    def deleted_by_user(self, obj):
        return obj.deleted_at is not None

    def has_add_permission(self, request):
        return False


@admin.register(AISettings)
class AISettingsAdmin(ModelAdmin):
    """
    Singleton config (always pk=1) - lets an admin change which AI
    provider/model the AI Assistant calls, and optionally override its API
    key, without touching environment variables or redeploying. Same
    singleton + read-through-cache pattern as apps/billing/models.py's
    TrialSettings/PricingSettings - saving clears the cache, so the very
    next chat request picks up the change.
    """
    form = AISettingsAdminForm
    list_display = ['provider', 'model_name', 'updated_at']
    fields = ['provider', 'model_name', 'custom_base_url', 'api_key_override', 'updated_at']
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        return not AISettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj, _created = AISettings.objects.get_or_create(pk=1)
        return redirect(reverse('admin:ai_aisettings_change', args=[obj.pk]))
