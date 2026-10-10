from decimal import Decimal

from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import (
    Subscription, SubscriptionStatus, TrialSettings, PlanPrice, SubscriptionPurchase, get_trial_period_days,
)
from .plans import PRO, FREE
from .services import mark_purchase_refunded


@admin.action(description='Grant free Pro access (no expiry, no payment)')
def grant_free_pro(modeladmin, request, queryset):
    """
    Comps the selected accounts onto Pro for free - a support gesture,
    promo, or partner account - without going through the upgrade flow or
    creating a SubscriptionPurchase (there is no real payment to record).
    Sets `is_complimentary=True`, which makes Subscription.maybe_expire()
    leave it alone permanently regardless of `current_period_end`.
    """
    now = timezone.now()
    count = queryset.update(
        plan=PRO,
        status=SubscriptionStatus.ACTIVE,
        billing_cycle=None,
        is_complimentary=True,
        cancel_at_period_end=False,
        current_period_start=now,
        current_period_end=None,  # complimentary access doesn't expire
        price_ngn=0,  # comped, not paying - must never count toward MRR
        provider='admin_grant',
    )
    modeladmin.message_user(request, f'Granted free Pro access to {count} account(s).')


@admin.action(description='Revoke Pro / move to Free')
def revoke_pro(modeladmin, request, queryset):
    """Undoes grant_free_pro (or any Pro subscription) - moves straight to Free, no grace period, since nothing was ever paid for. Historical SubscriptionPurchase rows are never touched."""
    count = queryset.update(
        plan=FREE,
        status=SubscriptionStatus.ACTIVE,
        billing_cycle=None,
        is_complimentary=False,
        cancel_at_period_end=False,
        current_period_start=None,
        current_period_end=None,
        price_ngn=0,
    )
    modeladmin.message_user(request, f'Moved {count} account(s) back to Free.')


@admin.action(description='Start/restart free trial (admin override)')
def start_trial_admin(modeladmin, request, queryset):
    """Same effect as a user starting their own trial, but callable on any selected account(s) regardless of has_used_trial/trial_phone - for a genuine support case."""
    now = timezone.now()
    count = queryset.update(
        plan=PRO,
        status=SubscriptionStatus.TRIAL,
        billing_cycle=None,
        trial_started_at=now,
        has_used_trial=True,
        is_complimentary=False,
        cancel_at_period_end=False,
        current_period_start=now,
        current_period_end=None,
        price_ngn=0,
        provider='',
    )
    modeladmin.message_user(request, f'Started a {get_trial_period_days()}-day trial for {count} account(s).')


@admin.action(description='Reset trial eligibility (lets them start a trial again)')
def reset_trial_eligibility(modeladmin, request, queryset):
    """Clears has_used_trial and the phone-number fingerprint without changing the account's current plan - for a genuine support case where someone should get another shot at a trial."""
    count = queryset.update(has_used_trial=False, trial_phone='')
    modeladmin.message_user(request, f'Reset trial eligibility for {count} account(s).')


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ['user', 'plan_badge', 'billing_cycle', 'status', 'price_badge', 'trial_badge', 'complimentary_badge', 'cancel_at_period_end', 'current_period_end', 'provider', 'updated_at']
    list_filter = ['plan', 'billing_cycle', 'status', 'is_complimentary', 'has_used_trial', 'provider']
    search_fields = ['user__email', 'user__name', 'provider_reference', 'trial_phone']
    readonly_fields = ['id', 'created_at', 'updated_at']
    actions = [grant_free_pro, revoke_pro, start_trial_admin, reset_trial_eligibility]
    fieldsets = (
        (None, {'fields': ('user', 'plan', 'billing_cycle', 'status', 'cancel_at_period_end', 'is_complimentary')}),
        (
            'Billing period',
            {
                'fields': ('current_period_start', 'current_period_end', 'price_ngn'),
                'description': (
                    'price_ngn is the price THIS subscriber locked in at their last purchase - not '
                    'necessarily today\u2019s live price (Revenue & Billing \u203a Plan prices can change after '
                    'they subscribed). See billing_subscription_purchases (below, in the Django admin '
                    'index) for the permanent, itemized history of every payment - this field only ever '
                    'reflects the CURRENT period.'
                ),
            },
        ),
        ('Free trial', {'fields': ('trial_started_at', 'has_used_trial', 'trial_phone', 'trial_started_ip')}),
        ('Payment provider', {'fields': ('provider', 'provider_reference')}),
        ('Meta', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    @admin.display(description='Plan')
    def plan_badge(self, obj):
        color = '#16a34a' if obj.effective_plan == PRO else '#6b7280'
        return format_html('<span style="font-weight:700;color:{}">{}</span>', color, obj.effective_plan)

    @admin.display(description='Comp?', boolean=True)
    def complimentary_badge(self, obj):
        return obj.is_complimentary

    @admin.display(description='Price')
    def price_badge(self, obj):
        if obj.price_ngn:
            return f'\u20a6{obj.price_ngn:,}'
        return '\u2014'

    @admin.display(description='Trial')
    def trial_badge(self, obj):
        if obj.is_trial_active:
            return format_html('<span style="font-weight:700;color:#d97706">{} day(s) left</span>', obj.trial_days_remaining)
        if obj.has_used_trial:
            return '\u2713 used'
        return '\u2014'


@admin.register(TrialSettings)
class TrialSettingsAdmin(ModelAdmin):
    """Singleton config (always pk=1) - THE control for "how long a free trial lasts for all users", live the moment it's saved (see models.py)."""
    list_display = ['trial_duration_days', 'updated_at']

    def has_add_permission(self, request):
        return not TrialSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj, _created = TrialSettings.objects.get_or_create(pk=1)
        return redirect(reverse('admin:billing_trialsettings_change', args=[obj.pk]))


class PlanPriceAdminForm(forms.ModelForm):
    """
    Prices are edited in NAIRA here (what a human thinks in) while the
    database keeps storing integer KOBO (what Paystack and all the money
    maths use - no float rounding anywhere). The conversion happens only in
    this form: `price_naira` in, `price_kobo` out.
    """
    price_naira = forms.DecimalField(
        label='Price (\u20a6 Naira)', min_value=Decimal('1'), max_digits=12, decimal_places=2,
        help_text='Enter the price in Naira, e.g. 5000 for \u20a65,000. It is stored in kobo automatically.',
    )

    class Meta:
        model = PlanPrice
        fields = ['billing_cycle', 'price_naira', 'currency', 'is_current', 'note']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['price_naira'].initial = (Decimal(self.instance.price_kobo) / 100).quantize(Decimal('0.01'))

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Decimal -> whole kobo without touching floats.
        instance.price_kobo = int((self.cleaned_data['price_naira'] * 100).to_integral_value())
        if commit:
            instance.save()
        return instance


@admin.register(PlanPrice)
class PlanPriceAdmin(ModelAdmin):
    """
    THE control for "how much does Monthly/6-Month/Annual cost right now" -
    just edit the Naira price on the row for the cycle you want to change and
    save; PlanPrice.save() takes care of invalidating the price cache, so
    it's live for the very next request. (You can also use "Add plan
    price" to create a whole new dated version instead, if you'd rather
    keep an explicit history entry per change - either way works, and
    every past PURCHASE stays exactly as it was regardless of which you
    use: see billing_subscription_purchases for that immutable history.)
    """
    form = PlanPriceAdminForm
    list_display = ['billing_cycle', 'price_display', 'is_current', 'note', 'created_by', 'created_at']
    list_filter = ['billing_cycle', 'is_current']
    ordering = ['billing_cycle', '-created_at']

    @admin.display(description='Price')
    def price_display(self, obj):
        return f'\u20a6{obj.price_kobo / 100:,.2f}'

    def get_readonly_fields(self, request, obj=None):
        base = ['created_by', 'created_at']
        if obj is not None:
            # billing_cycle must never change on an EXISTING row.
            # PlanPrice.save() keeps exactly one is_current=True row PER
            # CYCLE by un-setting every other row in that same cycle -
            # moving a row to a different cycle (or a stray "is_current"
            # toggle that leaves a cycle with none) would leave its old
            # cycle with zero current rows, and get_current_plan_price()
            # would then have nothing to serve for it. price_kobo/
            # is_current/note stay freely editable - that's the actual
            # "change today's price" fast path.
            return base + ['billing_cycle']
        return base

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.action(description='Mark as refunded / reversed (never deletes the record)')
def mark_refunded_action(modeladmin, request, queryset):
    count = 0
    for purchase in queryset.exclude(status=SubscriptionPurchase.Status.REFUNDED):
        mark_purchase_refunded(purchase, reason=f'Marked refunded from Django admin by {request.user.email}.')
        count += 1
    modeladmin.message_user(request, f'Marked {count} purchase(s) as refunded and reversed any related referral commission.')


@admin.register(SubscriptionPurchase)
class SubscriptionPurchaseAdmin(ModelAdmin):
    """
    The permanent, itemized payment ledger the spec requires: every
    successful purchase, the EXACT amount paid at the time (never
    recalculated from today's price), which billing cycle, and the
    referral (if any) it was attributed to. Fully read-only except the
    "mark refunded" action, which flips status without ever deleting the
    row - see apps.billing.services.mark_purchase_refunded.
    """
    list_display = ['user', 'billing_cycle', 'amount_display', 'payment_provider', 'status', 'is_renewal', 'subscription_start', 'subscription_expiry', 'created_at']
    list_filter = ['billing_cycle', 'payment_provider', 'status', 'is_renewal']
    search_fields = ['user__email', 'payment_reference']
    date_hierarchy = 'created_at'
    actions = [mark_refunded_action]
    readonly_fields = [
        'id', 'user', 'plan', 'billing_cycle', 'plan_price', 'amount_paid_kobo', 'currency',
        'payment_provider', 'payment_reference', 'status', 'subscription_start', 'subscription_expiry',
        'is_renewal', 'referral', 'refund_reason', 'refunded_at', 'created_at', 'updated_at',
    ]

    @admin.display(description='Amount paid')
    def amount_display(self, obj):
        return f'\u20a6{obj.amount_paid_ngn:,} {obj.currency}'

    def has_add_permission(self, request):
        return False  # purchases are only ever created by the payment flow, never hand-entered

    def has_delete_permission(self, request, obj=None):
        return False  # immutable financial history - see spec \u00a73/\u00a78/\u00a711
