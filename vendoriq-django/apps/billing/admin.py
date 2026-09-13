from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import Subscription, SubscriptionStatus, TrialSettings, PricingSettings, get_trial_period_days
from .plans import PRO, FREE


@admin.action(description='Grant free Pro access (no expiry, no payment)')
def grant_free_pro(modeladmin, request, queryset):
    """
    Comps the selected accounts onto Pro for free - a support gesture,
    promo, or partner account - without going through the (mock, or
    eventually real) upgrade flow. Sets `is_complimentary=True`, which
    makes Subscription.maybe_expire() leave it alone permanently
    regardless of `current_period_end` (see models.py) - so this doesn't
    quietly lapse the way a normal 30-day Pro period would.
    """
    now = timezone.now()
    count = queryset.update(
        plan=PRO,
        status=SubscriptionStatus.ACTIVE,
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
    """Undoes grant_free_pro (or any Pro subscription) - moves straight to Free, no grace period, since nothing was ever paid for."""
    count = queryset.update(
        plan=FREE,
        status=SubscriptionStatus.ACTIVE,
        is_complimentary=False,
        cancel_at_period_end=False,
        current_period_start=None,
        current_period_end=None,
        price_ngn=0,  # no longer paying
    )
    modeladmin.message_user(request, f'Moved {count} account(s) back to Free.')


@admin.action(description='Start/restart free trial (admin override)')
def start_trial_admin(modeladmin, request, queryset):
    """
    Same effect as a user starting their own trial (see
    entitlements.start_trial), but callable on any selected account(s)
    regardless of `has_used_trial` - a normal user only gets one trial ever,
    but a support agent should be able to grant another one deliberately
    (e.g. "sorry your trial glitched, here's a fresh one"). Uses
    get_trial_period_days() the same way the self-serve flow does, so it
    always matches the CURRENT value in Billing > Trial settings - not a
    number baked into this action's label, which would go stale the moment
    someone changed it (admin action descriptions are evaluated once, at
    import time, not per-request).
    """
    now = timezone.now()
    count = queryset.update(
        plan=PRO,
        status=SubscriptionStatus.TRIAL,
        trial_started_at=now,
        has_used_trial=True,
        is_complimentary=False,
        cancel_at_period_end=False,
        current_period_start=now,
        current_period_end=None,
        price_ngn=0,  # trialing, not paying - must never count toward MRR
        provider='',
    )
    modeladmin.message_user(request, f'Started a {get_trial_period_days()}-day trial for {count} account(s).')


@admin.action(description='Reset trial eligibility (lets them start a trial again)')
def reset_trial_eligibility(modeladmin, request, queryset):
    """Clears has_used_trial without changing the account's current plan - for a genuine support case where someone should get another shot at a trial."""
    count = queryset.update(has_used_trial=False)
    modeladmin.message_user(request, f'Reset trial eligibility for {count} account(s).')


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ['user', 'plan_badge', 'status', 'price_badge', 'trial_badge', 'complimentary_badge', 'cancel_at_period_end', 'current_period_end', 'provider', 'updated_at']
    list_filter = ['plan', 'status', 'is_complimentary', 'has_used_trial', 'provider']
    search_fields = ['user__email', 'user__name', 'provider_reference']
    readonly_fields = ['id', 'created_at', 'updated_at']
    # Select one or more rows in the list view -> Action dropdown at the
    # top. Free-Pro grants and trials are deliberately separate actions:
    # a grant never expires, a trial always does (length set in Billing >
    # Trial settings) - mixing them into one action would make it easy to
    # accidentally comp someone permanently when a time-limited trial was
    # intended, or vice versa.
    actions = [grant_free_pro, revoke_pro, start_trial_admin, reset_trial_eligibility]
    fieldsets = (
        (None, {'fields': ('user', 'plan', 'status', 'cancel_at_period_end', 'is_complimentary')}),
        (
            'Billing period',
            {
                'fields': ('current_period_start', 'current_period_end', 'price_ngn'),
                'description': (
                    'price_ngn is the price THIS subscriber locked in, captured at the moment they upgraded - '
                    'not necessarily today\u2019s Pro price (Revenue & Billing \u203a Pro plan price can change after '
                    'they subscribed). Editable here for a genuine support correction (e.g. an agreed discount); '
                    'MRR sums this field across paying subscribers rather than multiplying by the current price, '
                    'specifically so a price change doesn\u2019t retroactively inflate revenue nobody actually paid.'
                ),
            },
        ),
        ('Free trial (length is set platform-wide, not per account - see Billing > Trial settings)', {'fields': ('trial_started_at', 'has_used_trial')}),
        ('Payment provider (for when a real gateway is wired up)', {'fields': ('provider', 'provider_reference')}),
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
            return f'\u20a6{obj.price_ngn}/mo'
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
    """
    Singleton config (always pk=1) - this is THE control for "how long a
    free trial lasts for all users", live from the moment it's saved (see
    models.py::TrialSettings.save(), which clears the read-through cache on
    every save so the very next request picks up the new value - no
    redeploy, no waiting on a cache TTL).

    Changing this retroactively affects everyone CURRENTLY mid-trial too,
    not just future signups - because a trial's deadline is computed as
    trial_started_at + get_trial_period_days() at read time (see
    Subscription.is_trial_active), not stored as a fixed end date. That's
    a deliberate choice: "change the trial length for all users" reads as
    changing it for everyone under it right now, not just people who
    haven't started one yet.

    Registered as a singleton: there is exactly one row (pk=1, created
    on-demand by get_trial_period_days() the first time anything reads it,
    or by visiting this page). "Add" redirects straight to that row instead
    of offering to create a second one, and "Delete" is disabled - deleting
    the only settings row would just mean the next read silently recreates
    it at the model's default, which is more confusing than useful.
    """
    list_display = ['trial_duration_days', 'updated_at']

    def has_add_permission(self, request):
        # Only ever one row - if it already exists, there's nothing to add.
        return not TrialSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Skip the list view entirely - go straight to editing the one row
        # that matters, creating it first if this is the very first visit.
        obj, _created = TrialSettings.objects.get_or_create(pk=1)
        return redirect(reverse('admin:billing_trialsettings_change', args=[obj.pk]))


@admin.register(PricingSettings)
class PricingSettingsAdmin(ModelAdmin):
    """
    Singleton config (always pk=1) - this is THE control for "how much a
    NEW Pro upgrade costs", live from the moment it's saved (see
    models.py::PricingSettings.save(), which clears the read-through cache
    immediately - no redeploy, no waiting on a cache TTL).

    Deliberately does NOT retroactively change what existing paying
    subscribers are charged: get_pro_price_ngn() (and this admin) control
    what a NEW upgrade locks in going forward (Subscription page, upgrade
    modal, this page all reflect it immediately) - but each subscriber's
    OWN price is captured once, at the moment they upgrade, onto
    Subscription.price_ngn (see UpgradeView) and never re-read from here
    afterward. MRR sums that per-subscriber field rather than
    count * this value, specifically so changing this number can never
    inflate revenue nobody has actually agreed to pay.

    Same singleton pattern as TrialSettingsAdmin above: "Add" redirects
    straight to the one existing row, "Delete" is disabled.
    """
    list_display = ['pro_price_ngn', 'updated_at']

    def has_add_permission(self, request):
        return not PricingSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj, _created = PricingSettings.objects.get_or_create(pk=1)
        return redirect(reverse('admin:billing_pricingsettings_change', args=[obj.pk]))
