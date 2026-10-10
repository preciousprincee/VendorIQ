import uuid
from datetime import timedelta
from django.core.cache import cache
from django.db import models
from django.utils import timezone
from apps.authentication.models import User
from .plans import (
    FREE, PRO, PLAN_CHOICES, TRIAL_PERIOD_DAYS,
    BILLING_CYCLE_CHOICES, BILLING_CYCLE_ORDER, PRICE_SEED_KOBO,
)

TRIAL_SETTINGS_CACHE_KEY = 'billing:trial_duration_days'
PLAN_PRICE_CACHE_KEY_PREFIX = 'billing:plan_price'


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
    DEPRECATED - superseded by PlanPrice below.

    This used to hold a single "Pro price" for the whole product, back
    when VendorIQ only sold one monthly Pro plan. Now that Pro is sold in
    three billing cycles (Monthly/6-Month/Annual - see apps.billing.plans),
    a single price no longer makes sense, and nothing in the codebase
    reads or writes this model any more. It is kept ONLY so the existing
    database table/migration history isn't broken, and is intentionally
    NOT registered in Django Admin any more (editing it would silently do
    nothing). Safe to drop in a future migration once confirmed unused in
    every environment.
    """
    pro_price_ngn = models.PositiveIntegerField(default=5000)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_pricing_settings'
        verbose_name = 'Pricing settings (deprecated)'
        verbose_name_plural = 'Pricing settings (deprecated)'

    def __str__(self):
        return f'\u20a6{self.pro_price_ngn}/mo (deprecated, unused)'


class PlanPrice(models.Model):
    """
    A versioned price for one billing cycle (Monthly / 6-Month / Annual).
    This is THE centralized, database-backed pricing configuration the
    spec asks for - nowhere else in the codebase hardcodes a Naira amount
    for a paid plan.

    Prices are versioned: changing "the current price" for a cycle can be
    done either by editing this row's price_kobo directly from Django
    Admin (simplest - see PlanPriceAdmin), or by creating a NEW PlanPrice
    row with is_current=True (see save() below, which flips every older
    row for that cycle to is_current=False automatically) if you'd rather
    keep an explicit dated history of changes. Either way, every existing
    SubscriptionPurchase keeps its own recorded amount_paid_kobo regardless -
    that immutable history lives on SubscriptionPurchase, not here, so
    editing a PlanPrice row never rewrites what anyone already paid.

    Stored in kobo (1 Naira = 100 kobo) - an integer minor unit, never a
    float - so nothing here is ever subject to floating-point rounding
    error.
    """
    id = models.BigAutoField(primary_key=True)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES)
    price_kobo = models.PositiveBigIntegerField(
        help_text='Price in kobo (1 Naira = 100 kobo). E.g. \u20a65,000 = 500000.',
    )
    currency = models.CharField(max_length=3, default='NGN')
    is_current = models.BooleanField(
        default=True,
        help_text='The live price new purchases use for this cycle. Setting this on a new row '
                   'automatically un-sets it on every older row for the same cycle - existing '
                   'subscriptions/purchases are entirely unaffected either way.',
    )
    note = models.CharField(max_length=255, blank=True, help_text='Optional internal note, e.g. "Sept 2026 price increase".')
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_plan_prices'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['billing_cycle', 'is_current'])]
        verbose_name = 'Plan price'
        verbose_name_plural = 'Plan prices'

    def __str__(self):
        naira = self.price_kobo / 100
        state = 'current' if self.is_current else 'past'
        return f'{self.get_billing_cycle_display()} \u2014 \u20a6{naira:,.2f} ({state})'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            # Exactly one current price per cycle. This is what makes a
            # price change take effect for NEW purchases immediately
            # without ever touching a historical purchase record or an
            # older PlanPrice row's price_kobo.
            PlanPrice.objects.filter(billing_cycle=self.billing_cycle, is_current=True).exclude(pk=self.pk).update(is_current=False)
        cache.delete(f'{PLAN_PRICE_CACHE_KEY_PREFIX}:{self.billing_cycle}')


def get_current_plan_price(billing_cycle):
    """
    The price to actually charge/display right now for `billing_cycle`,
    as a plain dict {id, price_kobo, currency} (not a model instance, so
    callers can't accidentally mutate a "live" object and think they've
    changed the price - see PlanPrice.save() for how a price change is
    actually made). Seeds the very first PlanPrice row for a cycle from
    apps.billing.plans.PRICE_SEED_KOBO if none exists yet.
    """
    cache_key = f'{PLAN_PRICE_CACHE_KEY_PREFIX}:{billing_cycle}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    obj = PlanPrice.objects.filter(billing_cycle=billing_cycle, is_current=True).order_by('-created_at').first()
    if obj is None:
        # No row is flagged is_current for this cycle - shouldn't normally
        # happen (PlanPrice.save() keeps exactly one), but an admin could
        # get here by hand-unchecking "is current" on the only row for a
        # cycle. Fall back to the most recent price EVER recorded for this
        # cycle rather than jumping straight to reseeding the original
        # launch price below - silently reverting a live price back to its
        # launch-day value would be a much bigger, more dangerous surprise
        # than just treating the latest row as authoritative.
        obj = PlanPrice.objects.filter(billing_cycle=billing_cycle).order_by('-created_at').first()
    if obj is None:
        # Truly nothing has ever been recorded for this cycle (a fresh
        # install) - THIS is the only case that should ever seed from the
        # hardcoded launch price.
        obj = PlanPrice.objects.create(
            billing_cycle=billing_cycle,
            price_kobo=PRICE_SEED_KOBO[billing_cycle],
            is_current=True,
        )
    data = {'id': obj.id, 'price_kobo': obj.price_kobo, 'currency': obj.currency}
    cache.set(cache_key, data, 300)
    return data


def get_plan_pricing_catalog():
    """
    The full Monthly/6-Month/Annual pricing catalog, with the monthly-
    equivalent price computed for each cycle so the frontend never needs
    to do that division (and risk a float) itself. Backs GET
    /api/billing/plans/ and the pricing section of GET
    /api/billing/subscription/.
    """
    from .plans import BILLING_CYCLE_MONTHS, BILLING_CYCLE_LABELS
    catalog = []
    for cycle in BILLING_CYCLE_ORDER:
        price = get_current_plan_price(cycle)
        months = BILLING_CYCLE_MONTHS[cycle]
        monthly_equivalent_kobo = price['price_kobo'] // months  # integer division - no floats
        catalog.append({
            'billingCycle': cycle,
            'label': BILLING_CYCLE_LABELS[cycle],
            'billingPeriodMonths': months,
            'priceKobo': price['price_kobo'],
            'priceNgn': price['price_kobo'] // 100,
            'currency': price['currency'],
            'monthlyEquivalentNgn': monthly_equivalent_kobo // 100,
            'mostPopular': cycle == 'SIX_MONTH',
            'bestValue': cycle == 'ANNUAL',
        })
    return catalog


class SubscriptionStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    TRIAL = 'TRIAL', 'Trial'  # temporary Pro access, no payment - see trial_started_at below
    CANCELLED = 'CANCELLED', 'Cancelled'  # Pro, cancelled but still within paid period
    EXPIRED = 'EXPIRED', 'Expired'  # was Pro or Trial, period ended, now behaves as Free
    PAST_DUE = 'PAST_DUE', 'Past due'  # reserved for when a real payment gateway is wired up


class Subscription(models.Model):
    """
    One row per user - the backend's source of truth for what plan an
    account is CURRENTLY on (status/period/billing cycle). This is
    deliberately NOT the financial record of what was paid - that's
    SubscriptionPurchase below, one immutable row per successful payment.
    Subscription is derived/current state; SubscriptionPurchase is the
    permanent ledger. Every store-scoped limit check (products, staff)
    reads the STORE OWNER's subscription, not the acting staff member's,
    since the owner is who is paying: see apps/billing/entitlements.py.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')

    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=FREE)
    status = models.CharField(max_length=10, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE)

    # Which of the three billing cycles (Monthly/6-Month/Annual) the
    # CURRENT paid period was bought under. Null for Free, and for an
    # active trial (a trial has no billing cycle - it's not a purchase).
    # Set from the SubscriptionPurchase that activated/renewed this
    # subscription - see apps/billing/services.create_subscription_purchase.
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES, null=True, blank=True)

    # Null for Free (Free has no billing period). For Pro, the currently
    # paid-for window - `current_period_end` is what "renewal/expiry date"
    # means in the spec, and is exactly what a successful payment
    # (verify call or webhook) extends - see apps/billing/services.py.
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    # Set when a Pro user cancels - they keep Pro access until
    # current_period_end, then a scheduled downgrade (see maybe_expire
    # below) drops them to Free. Cancelling never triggers a refund and
    # never shortens the period they already paid for.
    cancel_at_period_end = models.BooleanField(default=False)

    # Where the payment that activated/renewed this subscription came
    # from. 'paystack' for a real payment, 'mock' for the no-real-money
    # dev fallback, 'admin_grant' for a complimentary grant.
    provider = models.CharField(max_length=30, blank=True, default='')
    provider_reference = models.CharField(max_length=255, blank=True, default='')

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
    # Trial-abuse signals, recorded (not silently discarded) at the moment
    # a trial starts, so a support agent can see WHY a second trial from
    # the same person was blocked, or spot a pattern across accounts. See
    # apps/billing/entitlements.py::start_trial for how these are used.
    # trial_phone in particular is what actually BLOCKS a repeat trial
    # (see start_trial) - IP alone is too noisy on shared/mobile networks
    # in Nigeria (CGNAT) to safely hard-block on, so it's recorded for
    # admin visibility only.
    trial_phone = models.CharField(max_length=20, blank=True, default='', db_index=True)
    trial_started_ip = models.GenericIPAddressField(null=True, blank=True)

    # The amount (in Naira, whole units - never a float) this subscriber
    # is CURRENTLY paying, captured from the SubscriptionPurchase that
    # activated/renewed them, at the moment that happened - never read
    # live from PlanPrice. This is what makes MRR honest: PlanPrice can
    # change at any time, but that must only affect what NEW purchases
    # cost, not retroactively "charge" existing paying customers more than
    # they agreed to. Always 0 for Free, Trial, and complimentary
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
        without going through this first.

        IMPORTANT: this only changes the CURRENT state - it never touches
        a SubscriptionPurchase, which is the permanent historical record
        of what was actually paid and stays untouched forever.
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


class SubscriptionPurchase(models.Model):
    """
    One row per successful subscription payment - the permanent,
    IMMUTABLE financial record the spec requires. Never edited after
    creation except to flip `status` if the payment is later refunded/
    reversed (see apps.billing.services.mark_purchase_refunded) - even
    then, amount_paid_kobo, subscription_start/expiry and every other
    commercial term stay exactly as they were at purchase time.

    Deliberately separate from Subscription (which only tracks CURRENT
    plan/status): a user's Subscription row is overwritten on every
    renewal, but their SubscriptionPurchase history never is - this is
    what lets a later price change never retroactively affect what an
    earlier purchase is recorded as costing.

    `payment_reference` is unique at the database level - this is the
    actual idempotency guarantee against duplicate webhook deliveries or
    a client retrying the verify call: a second attempt to create a
    purchase for the same reference always fails at the DB, never
    silently double-activates or double-counts revenue. See
    apps.billing.services.create_subscription_purchase.
    """
    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        REFUNDED = 'REFUNDED', 'Refunded'
        REVERSED = 'REVERSED', 'Reversed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscription_purchases')
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES, default=PRO)
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES)
    # Which PlanPrice version was current at the moment of purchase - kept
    # for traceability/audit only. SET_NULL (never CASCADE/PROTECT): a
    # PlanPrice row is never deleted in normal operation, but this
    # purchase's own amount_paid_kobo is the actual source of truth
    # regardless of whether this link survives.
    plan_price = models.ForeignKey(PlanPrice, null=True, blank=True, on_delete=models.SET_NULL, related_name='purchases')

    # The exact commercial terms of THIS purchase - never recalculated
    # from "today's price". Integer minor units (kobo), never a float.
    amount_paid_kobo = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default='NGN')

    payment_provider = models.CharField(max_length=30)  # 'paystack' or 'mock'
    payment_reference = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCESS)

    subscription_start = models.DateTimeField()
    subscription_expiry = models.DateTimeField()
    is_renewal = models.BooleanField(default=False, help_text='False for a user\'s first-ever successful purchase, True for every purchase after that.')

    # Referral attribution at the time of purchase, if any - kept even if
    # the ReferralCommission it produced is later reversed, so "was this
    # purchase referred" remains answerable from the purchase record
    # itself. SET_NULL rather than CASCADE: a referral record being
    # removed (it never is in normal operation) must not destroy the
    # payment history it's merely annotating.
    referral = models.ForeignKey('referrals.Referral', null=True, blank=True, on_delete=models.SET_NULL, related_name='subscription_purchases')

    refund_reason = models.CharField(max_length=255, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_subscription_purchases'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f'{self.user.email} \u2014 {self.get_billing_cycle_display()} \u20a6{self.amount_paid_ngn} ({self.status})'

    @property
    def amount_paid_ngn(self):
        return self.amount_paid_kobo // 100


class CheckoutSession(models.Model):
    """
    What a checkout was SUPPOSED to buy, recorded server-side at the moment
    PaystackInitializeView starts it - the only thing that lets us trust a
    later verify call or charge.success webhook.

    Why this exists: Paystack's inline popup is configured in the browser
    (public key, amount, reference, metadata - see UpgradeModal.jsx), so
    anybody can open the popup with THEIR OWN values - e.g. pay the minimum
    amount while claiming metadata billing_cycle=ANNUAL. Paystack would
    report that transaction as a perfectly genuine success, and (before this
    model) both the verify endpoint and the signed webhook believed the
    metadata and the paid amount without comparing them to any price - so a
    NGN 50 payment could buy a year of Pro. Now the cycle, price and owner
    of a payment come from THIS row, and a payment for less than
    `amount_kobo` (or in another currency) is refused.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='checkout_sessions')
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES)
    amount_kobo = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default='NGN')
    plan_price = models.ForeignKey(PlanPrice, null=True, blank=True, on_delete=models.SET_NULL, related_name='checkout_sessions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_checkout_sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} ({self.billing_cycle}, {self.amount_kobo} kobo)'
