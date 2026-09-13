import uuid
from datetime import timedelta
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from apps.authentication.models import User
from .plans import FREE, PRO, PLAN_CHOICES, TRIAL_PERIOD_DAYS, PRO_PRICE_NGN

TRIAL_SETTINGS_CACHE_KEY = 'billing:trial_duration_days'
PRICING_SETTINGS_CACHE_KEY = 'billing:pro_price_ngn'


class TrialSettings(models.Model):
    """
    Singleton (always pk=1) holding the CURRENT free trial length in days -
    the live, admin-editable version of apps/billing/plans.py's
    TRIAL_PERIOD_DAYS. Edit this from Django Admin (Revenue & Billing >
    Free trial length) to change the trial for every account - including
    everyone CURRENTLY mid-trial, not just future signups.

    That retroactive behavior falls out of how it's used, not anything
    special here: Subscription.is_trial_active/trial_days_remaining compute
    a trial's deadline as `trial_started_at + get_trial_period_days()` at
    read time (see below), rather than storing a fixed end date on the
    Subscription row - so there's nothing per-user to migrate when this
    number changes, every active trial is just re-measured against the new
    value on its next read.
    """
    trial_duration_days = models.PositiveIntegerField(default=TRIAL_PERIOD_DAYS)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_trial_settings'
        verbose_name = 'Trial settings'
        verbose_name_plural = 'Trial settings'

    def __str__(self):
        return f'{self.trial_duration_days}-day free trial'

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton - there is only ever one row
        super().save(*args, **kwargs)
        cache.delete(TRIAL_SETTINGS_CACHE_KEY)


def get_trial_period_days():
    """
    The trial length to actually use right now. Every place that used to
    import TRIAL_PERIOD_DAYS directly for a real calculation (not just
    docs/labels) should call this instead - it's what makes the admin's
    "Free trial length" setting live instead of requiring a redeploy.
    Cached briefly since this is read on effectively every entitlement
    check across the whole app; TrialSettings.save() clears the cache
    immediately so an admin edit takes effect on the very next request,
    not after the cache TTL expires.
    """
    cached = cache.get(TRIAL_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    obj, _created = TrialSettings.objects.get_or_create(pk=1, defaults={'trial_duration_days': TRIAL_PERIOD_DAYS})
    cache.set(TRIAL_SETTINGS_CACHE_KEY, obj.trial_duration_days, 300)
    return obj.trial_duration_days


class PricingSettings(models.Model):
    """
    Singleton (always pk=1) holding the price a NEW Pro upgrade costs right
    now, in Naira - the live, admin-editable version of
    apps/billing/plans.py's PRO_PRICE_NGN seed. Edit this from Django Admin
    (Revenue & Billing > Pro plan price) to change what a new upgrade
    costs - the Subscription page, the upgrade modal, and the admin's
    Revenue/Plans pages all reflect it immediately, with no redeploy,
    following the exact same live-setting pattern as TrialSettings above.

    Unlike TrialSettings, this is grandfathered: changing it does NOT
    retroactively change what an existing paying subscriber is charged.
    Each subscriber locks in whatever this value was at the moment they
    upgraded, onto their own Subscription.price_ngn (see
    apps/billing/views.py::UpgradeView) - MRR sums that per-subscriber
    field rather than count * this value (see
    vendoriq/admin_dashboard.py::compute_subscription_metrics), so a price
    change can only ever affect future upgrades, never inflate revenue
    nobody has actually agreed to pay.
    """
    pro_price_ngn = models.PositiveIntegerField(default=PRO_PRICE_NGN)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_pricing_settings'
        verbose_name = 'Pricing settings'
        verbose_name_plural = 'Pricing settings'

    def __str__(self):
        return f'\u20a6{self.pro_price_ngn}/mo'

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton - there is only ever one row
        super().save(*args, **kwargs)
        cache.delete(PRICING_SETTINGS_CACHE_KEY)


def get_pro_price_ngn():
    """
    The Pro price to actually charge/display right now. Everywhere that
    used to read PLANS[PRO]['price_ngn'] or the PRO_PRICE_NGN env var
    directly for a real calculation (not just a code comment) should go
    through apps.billing.plans.get_plan_config(PRO)['price_ngn'] instead,
    which calls this - same cache-with-immediate-invalidation pattern as
    get_trial_period_days() above.
    """
    cached = cache.get(PRICING_SETTINGS_CACHE_KEY)
    if cached is not None:
        return cached
    obj, _created = PricingSettings.objects.get_or_create(pk=1, defaults={'pro_price_ngn': PRO_PRICE_NGN})
    cache.set(PRICING_SETTINGS_CACHE_KEY, obj.pro_price_ngn, 300)
    return obj.pro_price_ngn


class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    TRIAL = 'TRIAL', 'Trial'  # temporary Pro access, no payment - see trial_started_at below
    CANCELLED = 'CANCELLED', 'Cancelled'  # Pro, cancelled but still within paid period
    EXPIRED = 'EXPIRED', 'Expired'  # was Pro or Trial, period ended, now behaves as Free
    PAST_DUE = 'PAST_DUE', 'Past due'  # reserved for when a real payment gateway is wired up


class Subscription(models.Model):
    """
    One row per user - the backend's source of truth for what plan an
    account is on. Every store-scoped limit check (products, staff) reads
    the STORE OWNER's subscription, not the acting staff member's, since the
    owner is who is paying: see apps/billing/entitlements.py.

    Deliberately NOT a payment record - this only tracks plan/status/period.
    A real payment integration (Paystack/Flutterwave) would create a
    separate Payment/Transaction model that references this one and updates
    `status`/`current_period_end` via a webhook - see `provider` and
    `provider_reference` below, which exist now specifically so that wiring
    happens without changing this model's shape.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')

    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=FREE)
    status = models.CharField(max_length=10, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE)

    # Null for Free (Free has no billing period). For Pro, the currently
    # paid-for window - `current_period_end` is what "renewal/end date"
    # means in the spec, and is what a real payment webhook would extend on
    # each successful charge.
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # Set when a Pro user cancels - they keep Pro access until
    # current_period_end, then a scheduled downgrade (see
    # entitlements.sync_expired_subscriptions) drops them to Free.
    cancel_at_period_end = models.BooleanField(default=False)

    # Where a real payment gateway integration hooks in later. Kept as plain
    # nullable fields (not a FK to a Payment model, which doesn't exist yet)
    # so today's mock upgrade flow and tomorrow's Paystack/Flutterwave
    # integration write to the exact same columns - no migration needed to
    # "turn on" real payments, just a new view that sets these instead of
    # the mock upgrade view.
    provider = models.CharField(max_length=30, blank=True, default='')  # e.g. 'paystack', 'flutterwave', 'mock', 'admin_grant'
    provider_reference = models.CharField(max_length=255, blank=True, default='')  # gateway subscription/customer id

    # Set when platform staff comp a user onto Pro from the Django admin
    # (see admin.py's "Grant free Pro access" action) - e.g. a promo, a
    # partner store, a support goodwill gesture. A comped subscription never
    # auto-expires via maybe_expire() below regardless of
    # current_period_end, and is visually distinct in the admin so nobody
    # mistakes it for a real paid subscription when looking at revenue.
    is_complimentary = models.BooleanField(default=False)

    # Free trial - gives Pro access for the current trial length
    # (get_trial_period_days() above, live-editable from Django Admin)
    # without payment. `trial_started_at` is the only thing stored; the
    # deadline is computed as trial_started_at + get_trial_period_days() at
    # read time (see is_trial_active below) rather than a stored
    # current_period_end - that is what makes changing the trial length in
    # TrialSettings retroactively change the remaining time for every
    # account currently mid-trial, not just future ones. `has_used_trial`
    # prevents a Free user from repeatedly restarting a trial to get
    # permanent free Pro access; it's set the moment a trial starts and is
    # never cleared automatically (an admin can reset it - see admin.py's
    # "Reset trial eligibility" action - for support cases).
    trial_started_at = models.DateTimeField(null=True, blank=True)
    has_used_trial = models.BooleanField(default=False)

    # The Pro price this subscriber actually locked in, at the moment they
    # last upgraded (or an admin last granted/renewed them) - captured from
    # get_pro_price_ngn() AT THAT MOMENT, not read live. This is what makes
    # MRR honest: PricingSettings can change at any time (Django Admin >
    # Revenue & Billing > Pro plan price), but that must only affect what
    # NEW upgrades cost, not retroactively "charge" existing paying
    # customers more than they agreed to - see
    # vendoriq/admin_dashboard.py::compute_subscription_metrics, which sums
    # this field across paying subscribers rather than doing
    # count * current_price. Always 0 for Free, Trial, and complimentary
    # subscriptions - none of those represent real payment.
    price_ngn = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions'

    def __str__(self):
        return f'{self.user.email} - {self.plan} ({self.status})'

    @property
    def is_trial_active(self):
        """True while a started trial is still within the current trial length (get_trial_period_days()) of its start - see the field comment above for why this isn't a stored end date."""
        if self.status != SubscriptionStatus.TRIAL or not self.trial_started_at:
            return False
        return timezone.now() < self.trial_started_at + timedelta(days=get_trial_period_days())

    @property
    def trial_days_remaining(self):
        """Whole days left in an active trial, for UI copy like "3 days left in your trial" - 0 when not on an active trial."""
        if not self.is_trial_active:
            return 0
        remaining = (self.trial_started_at + timedelta(days=get_trial_period_days())) - timezone.now()
        return max(0, remaining.days + (1 if remaining.seconds > 0 else 0))

    @property
    def is_pro_active(self):
        """
        True Pro entitlement check: on the Pro plan, status ACTIVE or
        CANCELLED-but-not-yet-expired (cancellation takes effect at period
        end, not immediately), and not past the paid period. A
        complimentary grant is always active regardless of period_end -
        it's not tied to a billing cycle at all. An active trial also
        grants full Pro access for its duration, same as a paid
        subscription - see is_trial_active above.
        """
        if self.plan != PRO:
            return False
        if self.is_complimentary:
            return True
        if self.status == SubscriptionStatus.TRIAL:
            return self.is_trial_active
        if self.status == SubscriptionStatus.EXPIRED:
            return False
        if self.current_period_end and self.current_period_end < timezone.now():
            return False
        return True

    @property
    def effective_plan(self):
        """
        The plan to actually enforce limits/features against right now.
        Distinct from `.plan`, which is left as PRO on an expired
        subscription until the next sync/access check flips it - see
        entitlements.get_subscription(), which calls
        maybe_expire() before returning. Most callers should use
        get_subscription()/effective_plan rather than `.plan` directly.
        """
        return PRO if self.is_pro_active else FREE

    def maybe_expire(self):
        """
        Lazily downgrade an expired Pro subscription (paid or trial) to
        Free. Called on every read (see entitlements.get_subscription)
        instead of via a cron/celery-beat job - simpler to reason about for
        a first version, and correct because nothing ever checks `.plan`
        without going through this first. A scheduled task can be added
        later without changing this model if a "your trial is about to
        expire" email/notification needs a cron trigger independent of a
        request.
        """
        if (
            self.plan == PRO
            and not self.is_complimentary
            and self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED)
            and self.current_period_end
            and self.current_period_end < timezone.now()
        ):
            self.plan = FREE
            self.status = SubscriptionStatus.EXPIRED
            self.cancel_at_period_end = False
            self.price_ngn = 0  # no longer paying - don't let a stale locked-in price inflate MRR
            self.save(update_fields=['plan', 'status', 'cancel_at_period_end', 'price_ngn', 'updated_at'])
        elif (
            self.status == SubscriptionStatus.TRIAL
            and self.trial_started_at
            and timezone.now() >= self.trial_started_at + timedelta(days=get_trial_period_days())
        ):
            self.plan = FREE
            self.status = SubscriptionStatus.EXPIRED
            self.save(update_fields=['plan', 'status', 'updated_at'])
        return self
