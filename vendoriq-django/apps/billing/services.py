"""
The one place a successful Pro payment turns into subscription access.

Both the client-triggered Paystack verify flow and the Paystack charge
webhook (apps/billing/views.py) - and the mock dev-only upgrade flow - all
funnel through create_subscription_purchase() below, so there is exactly
one code path that can activate/renew a subscription. That is what makes
"prevent duplicate subscription activation" and "make payment processing
idempotent" (spec \u00a711) true by construction rather than by convention.
"""
import calendar
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from vendoriq import analytics
from .models import Subscription, SubscriptionStatus, SubscriptionPurchase
from .plans import PRO, BILLING_CYCLE_MONTHS

logger = logging.getLogger(__name__)


def add_months(dt, months):
    """
    Calendar-correct "N months from now": 26 Sept 2026 + 12 months = 26
    Sept 2027, not "now + 365 days" (which drifts across leap years and
    doesn't match how a person thinks about an annual plan). Clamps the
    day to the target month's actual length (e.g. 31 Jan + 1 month -> 28/29
    Feb), the same rule every real calendar uses.
    """
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


class DuplicatePaymentReference(Exception):
    """Raised (internally, never to callers) when a payment_reference is reused for a DIFFERENT user than it was already recorded against - a sign of tampering, not a normal retry."""


def create_subscription_purchase(*, user, billing_cycle, amount_paid_kobo, currency, payment_provider, payment_reference, plan_price_id=None, referral=None):
    """
    Idempotently records a successful payment as a permanent
    SubscriptionPurchase row and activates/extends the user's Pro
    subscription accordingly.

    Idempotency: `payment_reference` is unique at the database level (see
    SubscriptionPurchase.Meta). If this exact reference was already
    recorded - a webhook redelivery, the client's verify call racing the
    webhook, or a client retry - this returns the EXISTING purchase and
    does nothing further, rather than double-activating the subscription
    or double-crediting a referral commission. Returns (purchase, created).

    Renewal math: if the user already has an unexpired, non-complimentary
    Pro period, the new period is added ON TOP of the existing expiry
    (never from "now") - paying early (or a fast webhook+verify race) can
    only ever extend access, never shorten or reset what was already paid
    for. A lapsed/expired subscription (or a first-ever purchase) starts
    fresh from now.

    IMPORTANT: only the DB-mutation part of this runs inside a
    transaction/row-lock (the `with transaction.atomic()` block below).
    Referral-commission processing runs strictly AFTER that block commits,
    on purpose: process_referral_commission -> attempt_payout can make a
    real Paystack Transfer API call, and a slow/failed external HTTP call
    must never (a) hold the Subscription row lock open, blocking every
    other webhook/verify call for this same user for however long Paystack
    takes to respond, or (b) risk a later rollback discarding the DB
    record of a payout that has ALREADY gone out in the real world - the
    money and the database must never be able to disagree like that.
    """
    existing = SubscriptionPurchase.objects.filter(payment_reference=payment_reference).first()
    if existing is not None:
        return existing, False

    now = timezone.now()
    purchase = None

    with transaction.atomic():
        sub, _ = Subscription.objects.get_or_create(user=user)
        # select_for_update inside the atomic block: two near-simultaneous
        # calls for the SAME user (e.g. a webhook and a verify call landing
        # at once for two different, legitimate purchases) must not both
        # read the same "current expiry" and both compute the same
        # base_start - this serializes them so the second one correctly
        # extends from what the first one just wrote.
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)

        base_start = (
            sub.current_period_end
            if (sub.plan == PRO and sub.current_period_end and sub.current_period_end > now and not sub.is_complimentary)
            else now
        )
        months = BILLING_CYCLE_MONTHS[billing_cycle]
        expiry = add_months(base_start, months)
        is_renewal = SubscriptionPurchase.objects.filter(user=user, status=SubscriptionPurchase.Status.SUCCESS).exists()
        # Referral-eligibility specifically needs a NARROWER question than
        # is_renewal above: "is this the referred user's first REAL,
        # money-changing purchase" - not just "first successful purchase
        # of any kind." A purchase made through the mock/dev-only flow
        # (payment_provider='mock') still creates a SubscriptionPurchase
        # row with status=SUCCESS (so is_renewal, and general reporting,
        # correctly treat it as "they already had Pro before"), but it
        # must NEVER be able to consume a referral's one-time commission
        # slot - a free demo upgrade is not the "initial successful paid
        # subscription" the spec's referral commission is for. Computed
        # here, under the same row lock as is_renewal, so it has the same
        # race-safety guarantee (see process_referral_commission in
        # apps/referrals/services.py for why an independent, unlocked
        # re-check later would be wrong).
        is_first_real_purchase = payment_provider == 'paystack' and not SubscriptionPurchase.objects.filter(
            user=user, status=SubscriptionPurchase.Status.SUCCESS, payment_provider='paystack',
        ).exists()

        # Link the purchase to the buyer's referral record (nothing passed
        # one in, so SubscriptionPurchase.referral was always NULL and the
        # "purchases from referrals" view in admin stayed empty).
        if referral is None and payment_provider == 'paystack':
            from apps.referrals.models import Referral
            referral = Referral.objects.filter(referred_user=user).first()

        try:
            with transaction.atomic():  # nested = a SAVEPOINT, so a failed create() here doesn't poison the outer transaction
                purchase = SubscriptionPurchase.objects.create(
                    user=user,
                    plan=PRO,
                    billing_cycle=billing_cycle,
                    plan_price_id=plan_price_id,
                    amount_paid_kobo=amount_paid_kobo,
                    currency=currency,
                    payment_provider=payment_provider,
                    payment_reference=payment_reference,
                    status=SubscriptionPurchase.Status.SUCCESS,
                    subscription_start=base_start,
                    subscription_expiry=expiry,
                    is_renewal=is_renewal,
                    referral=referral,
                )
        except IntegrityError:
            # Lost a race against a concurrent identical webhook/verify call
            # for this exact reference - the other call already created (or
            # is about to commit) the real row. Never treat this as an
            # error, and never apply this branch's own sub.* changes below.
            logger.info('SubscriptionPurchase for reference=%s already created concurrently - returning existing row.', payment_reference)
            purchase = None

        if purchase is not None:
            sub.plan = PRO
            sub.status = SubscriptionStatus.ACTIVE
            sub.billing_cycle = billing_cycle
            sub.current_period_start = base_start
            sub.current_period_end = expiry
            sub.cancel_at_period_end = False
            sub.is_complimentary = False
            sub.provider = payment_provider
            sub.provider_reference = payment_reference
            sub.price_ngn = amount_paid_kobo // 100
            sub.save()

    if purchase is None:
        return SubscriptionPurchase.objects.get(payment_reference=payment_reference), False

    logger.info(
        'Subscription purchase recorded: user=%s cycle=%s amount_kobo=%s provider=%s reference=%s renewal=%s',
        user.id, billing_cycle, amount_paid_kobo, payment_provider, payment_reference, is_renewal,
    )

    # One event per real purchase, wherever it was confirmed (browser verify call OR Paystack webhook):
    # only the call that created the row reaches this line, so a redelivered webhook is never counted twice.
    # The dev-only mock upgrade moves no money, so it is not a purchase and must not inflate revenue.
    if payment_provider != 'mock':
        analytics.capture(
            user, 'subscription_purchased',
            {'billing_cycle': billing_cycle, 'amount_ngn': amount_paid_kobo // 100, 'currency': currency,
             'provider': payment_provider, 'is_renewal': is_renewal},
            set_props={'plan': 'PRO'},
        )

    # Everything above has committed by this point - the row lock is
    # released and the purchase/subscription are durably saved regardless
    # of what happens next. ONLY NOW do we do the slow/external part.
    # Referral commissions only ever apply to REAL money (provider=
    # 'paystack') - the mock dev-only flow has no real revenue to share.
    # Deliberately not allowed to break the purchase itself: a
    # referral-side failure must never turn into "the paying customer's
    # payment failed."
    if payment_provider == 'paystack':
        try:
            from apps.referrals.services import process_referral_commission
            process_referral_commission(purchase, is_first_real_purchase=is_first_real_purchase)
        except Exception:
            logger.error('Referral commission processing failed for purchase %s (payment already succeeded)', purchase.id, exc_info=True)

    return purchase, True


def mark_purchase_refunded(purchase, reason=''):
    """
    Marks a SubscriptionPurchase as refunded/reversed and reverses any
    referral commission it produced - WITHOUT deleting either record
    (spec \u00a78: "never delete historical financial records merely because
    a transaction was reversed"). Does NOT touch the user's current
    subscription access/expiry - that is a deliberate product decision
    left to an admin/support action, since a refund doesn't automatically
    mean access should be revoked mid-period; the historical amount paid
    is what changes, not the (already-granted) access window.

    Both writes happen in one transaction: no external calls are involved
    here (unlike create_subscription_purchase), so there's no reason NOT
    to make "purchase marked refunded" and "its commission reversed" an
    all-or-nothing pair - a crash between the two separate saves would
    otherwise leave a refunded purchase with a commission that still looks
    payable.
    """
    with transaction.atomic():
        if purchase.status == SubscriptionPurchase.Status.SUCCESS:
            purchase.status = SubscriptionPurchase.Status.REFUNDED
            purchase.refund_reason = reason[:255]
            purchase.refunded_at = timezone.now()
            purchase.save(update_fields=['status', 'refund_reason', 'refunded_at', 'updated_at'])
            logger.info('SubscriptionPurchase %s marked refunded: %s', purchase.id, reason)

        from apps.referrals.services import reverse_commissions_for_reference
        reverse_commissions_for_reference(purchase.payment_reference, reason=reason or 'Source payment refunded/reversed.')
