from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from unfold.admin import ModelAdmin
from .models import ReferralSettings, PayoutAccount, Referral, ReferralCommission
from .services import reverse_commissions_for_reference


@admin.register(ReferralSettings)
class ReferralSettingsAdmin(ModelAdmin):
    """Singleton (always pk=1) - same pattern as TrialSettings/PlanPrice."""
    list_display = ['enabled', 'commission_percent', 'updated_at']
    fields = ['enabled', 'commission_percent', 'updated_at']
    readonly_fields = ['updated_at']

    def has_add_permission(self, request):
        return not ReferralSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj, _created = ReferralSettings.objects.get_or_create(pk=1)
        return redirect(reverse('admin:referrals_referralsettings_change', args=[obj.pk]))


class CommissionInline(admin.TabularInline):
    model = ReferralCommission
    extra = 0
    can_delete = False
    fields = ['amount_ngn', 'status', 'failure_reason', 'paid_at', 'reversed_at']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Referral)
class ReferralAdmin(ModelAdmin):
    list_display = ['referrer', 'referred_user', 'code_used', 'commission_status', 'created_at']
    search_fields = ['referrer__email', 'referred_user__email', 'code_used']
    list_filter = ['created_at']
    inlines = [CommissionInline]

    @admin.display(description='Commission')
    def commission_status(self, obj):
        commission = obj.commissions.exclude(status=ReferralCommission.Status.REVERSED).first()
        return commission.status if commission else '\u2014 (no paid subscription yet)'


@admin.action(description='Reverse commission(s) (payment was refunded)')
def reverse_commissions_action(modeladmin, request, queryset):
    count = 0
    for commission in queryset.exclude(status=ReferralCommission.Status.REVERSED):
        reverse_commissions_for_reference(commission.source_reference, reason=f'Manually reversed from Django admin by {request.user.email}.')
        count += 1
    modeladmin.message_user(request, f'Reversed {count} commission(s).')


@admin.register(ReferralCommission)
class ReferralCommissionAdmin(ModelAdmin):
    """
    Where to check "why hasn't X been paid" - failure_reason usually says
    exactly what Paystack rejected (bad recipient, insufficient balance,
    OTP still enabled, etc). A FAILED or long-PROCESSING row here is worth
    a look before a referrer asks about it. Exactly one commission
    (excluding REVERSED) can ever exist per referral - see
    apps.referrals.services.process_referral_commission.
    """
    list_display = ['referral', 'amount_ngn', 'status', 'created_at', 'paid_at', 'reversed_at']
    list_filter = ['status']
    search_fields = ['referral__referrer__email', 'source_reference', 'paystack_transfer_code']
    actions = [reverse_commissions_action]
    readonly_fields = [
        'referral', 'source_reference', 'subscription_purchase', 'amount_ngn',
        'paystack_transfer_code', 'created_at', 'updated_at',
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # immutable financial history - reverse it instead (see the action above)


@admin.register(PayoutAccount)
class PayoutAccountAdmin(ModelAdmin):
    list_display = ['user', 'bank_name', 'masked_account_number', 'account_name', 'updated_at']
    search_fields = ['user__email', 'account_name']
    readonly_fields = ['paystack_recipient_code', 'created_at', 'updated_at']

    def masked_account_number(self, obj):
        return f'\u2022\u2022\u2022\u2022\u2022\u2022{obj.account_number[-4:]}'
    masked_account_number.short_description = 'Account number'
