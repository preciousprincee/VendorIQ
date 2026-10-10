import uuid
from decimal import Decimal, ROUND_DOWN
from django.core.cache import cache
from django.db import models
from apps.authentication.models import User

REFERRAL_SETTINGS_CACHE_KEY = 'referrals:settings'


class ReferralSettings(models.Model):
    """
    Singleton (always pk=1) - same pattern as apps/billing/models.py's
    TrialSettings/PlanPrice: admin-editable, read-through-cached, takes
    effect on the very next referral-eligible payment with no redeploy.
    """
    enabled = models.BooleanField(
        default=True,
        help_text='Master switch for the whole referral program. Turning this off stops NEW referral '
                   'signups and NEW commissions from being created everywhere in the app (registration '
                   'form, Google sign-up, and every Pro payment) - it does NOT stop already-earned '
                   'commissions from being paid out; money already owed to a referrer keeps processing '
                   'normally. See apps/referrals/services.py for exactly where this is checked.',
    )
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('20.00'),
        help_text="% of the referred user's FIRST successful paid subscription that the referrer earns. "
                  "This is a ONE-TIME commission, not recurring - a referred user's second purchase, "
                  "renewal, or upgrade never generates a further commission for the same referral. "
                  "See apps/referrals/services.py::process_referral_commission.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'referral_settings'
        verbose_name = 'Referral settings'
        verbose_name_plural = 'Referral settings'

    def __str__(self):
        status = 'ON' if self.enabled else 'OFF'
        return f'{status} \u2014 {self.commission_percent}% of first purchase only'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(REFERRAL_SETTINGS_CACHE_KEY)


def get_referral_settings():
    cached = cache.get(REFERRAL_SETTINGS_CACHE_KEY)
    if cached is None:
        obj, _created = ReferralSettings.objects.get_or_create(pk=1)
        cached = {'enabled': obj.enabled, 'commission_percent': obj.commission_percent}
        cache.set(REFERRAL_SETTINGS_CACHE_KEY, cached, 300)
    return cached


class PayoutAccount(models.Model):
    """
    Where a referrer's commission gets paid - one per user. account_name is
    what Paystack's own /bank/resolve returned for this account_number,
    never free-typed, so we're never wiring money based on a typo (Paystack
    itself also re-validates this when the transfer recipient is created).
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='payout_account')
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=255)  # Paystack-verified, not user-entered
    paystack_recipient_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'referral_payout_accounts'

    def __str__(self):
        return f'{self.user.email} \u2192 {self.bank_name} ({self.account_number[-4:]})'


class Referral(models.Model):
    """
    One row per successfully-referred signup - created once, at
    registration (see apps/referrals/services.py::record_referral_if_applicable),
    and never re-attributed afterwards even if the referral code field
    changes later.
    """
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='referrals_made')
    referred_user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='referred_by_record')
    code_used = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'referrals'

    def __str__(self):
        return f'{self.referrer.email} referred {self.referred_user.email}'


class ReferralCommission(models.Model):
    """
    At most ONE non-reversed row per Referral, ever - the commission is
    for the referred user's INITIAL successful paid subscription only, and
    is explicitly NOT recurring (spec \u00a74/\u00a75). Created by
    apps/referrals/services.py::process_referral_commission, called from
    apps/billing/services.create_subscription_purchase right after a REAL
    (provider='paystack') payment is recorded - never for a free trial
    (which has no payment) and never for the mock dev-only flow.

    A commission whose source payment is later refunded is marked
    REVERSED (never deleted - see apps.referrals.services.reverse_commissions_for_reference)
    and does NOT count against the "only one, ever" rule, so a genuinely
    new first purchase after a refunded one is still eligible.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending (no payout account yet)'
        PROCESSING = 'PROCESSING', 'Transfer initiated'
        PAID = 'PAID', 'Paid'
        FAILED = 'FAILED', 'Failed'
        REVERSED = 'REVERSED', 'Reversed (source payment refunded)'

    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name='commissions')
    # The Paystack transaction reference of the payment that earned this
    # commission - together with the unique_together below, this is what
    # makes crediting idempotent if a payment's verify/webhook path somehow
    # runs twice for the exact same payment.
    source_reference = models.CharField(max_length=100)
    # Traceability to the exact purchase this commission was computed
    # from - nullable/SET_NULL since amount_ngn below is the durable
    # record even if this link is ever lost.
    subscription_purchase = models.ForeignKey(
        'billing.SubscriptionPurchase', null=True, blank=True, on_delete=models.SET_NULL, related_name='referral_commissions',
    )
    amount_ngn = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    paystack_transfer_code = models.CharField(max_length=100, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'referral_commissions'
        unique_together = [('referral', 'source_reference')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.referral.referrer.email} \u2014 \u20a6{self.amount_ngn} ({self.status})'


def compute_commission_amount_ngn(amount_paid_kobo):
    """
    20% (or whatever ReferralSettings.commission_percent currently is) of
    the amount ACTUALLY paid, in kobo - never a hardcoded plan price.
    Computed via Decimal (never float) and rounded DOWN to the kobo, never
    up - a referral program that rounds in its own favor against the
    referrer erodes trust in the numbers it shows them for no real
    financial benefit (the difference is fractions of a kobo). Returns a
    Decimal Naira amount suitable for ReferralCommission.amount_ngn.
    """
    settings_ = get_referral_settings()
    amount_ngn = Decimal(amount_paid_kobo) / Decimal('100')
    raw = amount_ngn * settings_['commission_percent'] / Decimal('100')
    return raw.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
