import logging
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from .models import Referral, ReferralCommission, PayoutAccount, get_referral_settings, compute_commission_amount_ngn
from . import paystack
from apps.authentication.phone import normalize_phone

logger = logging.getLogger(__name__)


def record_referral_if_applicable(new_user, referral_code):
    """
    Called once, at registration (see apps/authentication/serializers.py
    and apps/authentication/social_views.py for the email/password and
    Google sign-up paths respectively). `referral_code` is the REFERRER'S
    PHONE NUMBER (a user's phone number is their referral code - see
    User.save()), typed however the new user likes: "0801 234 5678",
    "+234 801 234 5678" and "8012345678" all match the same referrer. If it
    belongs to a DIFFERENT existing user, permanently links new_user as
    their referral. Silently does nothing for a blank, unrecognised, or
    self-referral code as far as the SIGNUP response goes - referral
    attribution should never fail registration itself over a bad code - but
    every reason for NOT attributing is logged (at info level) so "why
    didn't my referral show up in admin" is answerable from the logs rather
    than a guess.
    """
    if not referral_code:
        return
    if not get_referral_settings()['enabled']:
        logger.info('Referral code %r supplied for %s but the referral program is currently disabled.', referral_code, new_user.email)
        return
    code = normalize_phone(referral_code)
    if not code:
        logger.info('Referral code %r supplied for %s is not a valid phone number - no referral recorded.', referral_code, new_user.email)
        return

    from apps.authentication.models import User
    referrer = User.objects.filter(referral_code=code).first()
    if referrer is None:
        logger.info('Referral code %r supplied for %s does not match any user - no referral recorded.', code, new_user.email)
        return
    if referrer.id == new_user.id:
        logger.info('User %s attempted to self-refer with their own code - ignored.', new_user.email)
        return

    _referral, created = Referral.objects.get_or_create(referred_user=new_user, defaults={'referrer': referrer, 'code_used': code})
    if created:
        logger.info('Referral recorded: %s referred %s (code %s).', referrer.email, new_user.email, code)
    else:
        logger.info('User %s already has a referral attribution - code %r from this signup was ignored.', new_user.email, code)


def process_referral_commission(purchase, is_first_real_purchase):
    """
    Called from apps/billing/services.create_subscription_purchase right
    after a REAL (provider='paystack') Pro purchase is recorded - never
    for a free trial (which never reaches this function - trials create no
    SubscriptionPurchase at all) and never for the 'mock' dev-only flow,
    which has no real money behind it to share.

    ONE-TIME commission rule (spec \u00a74/\u00a75): a referral earns a commission
    only from the referred user's INITIAL successful paid subscription -
    never from a renewal, a second purchase, or an upgrade. This is
    enforced two ways, both server-side, neither trusting the caller:
      1. `is_first_real_purchase` must be True. That flag is computed
         atomically under the Subscription row lock at purchase-creation
         time (apps.billing.services.create_subscription_purchase),
         scoped specifically to payment_provider='paystack' purchases -
         deliberately NOT the more general SubscriptionPurchase.is_renewal
         field, and NOT re-derived here via an independent query. Two
         distinct reasons, both important:
           - Racy re-derivation: if two purchases for the same user land
             close together, each one's referral processing runs only
             AFTER its own DB transaction has committed (see
             create_subscription_purchase for why), so by the time
             purchase A's commission check runs, purchase B may already
             exist in the database - an independent re-check here could
             see B and wrongly conclude A "isn't first" (and vice versa),
             silently skipping the commission entirely.
           - is_renewal counts ANY prior successful purchase, including a
             'mock' (no real money) one - which correctly makes it "was
             this user already on Pro before" for general bookkeeping, but
             would be WRONG here: a free demo upgrade must never occupy a
             referral's one-time commission slot. A user who got a mock
             upgrade (e.g. before Paystack was configured) and later makes
             their first REAL purchase must still be eligible.
      2. The referral must not already have a non-REVERSED commission (a
         belt-and-suspenders check - (1) alone would already guarantee
         this in the normal case, but this also correctly makes a
         genuinely new first purchase, after an earlier one was refunded,
         eligible again).

    Idempotent against duplicate webhook/verify calls for the SAME
    payment: the unique_together on (referral, source_reference), plus the
    .exists() check below, means calling this twice for the same
    `purchase` is a safe no-op, never a double credit.
    """
    try:
        referral = purchase.user.referred_by_record
    except Referral.DoesNotExist:
        return

    settings_ = get_referral_settings()
    if not settings_['enabled']:
        return  # program is switched off - no NEW commissions accrue; anything already PENDING still gets paid by sweep_pending_payouts/attempt_payout below, unaffected by this flag

    if ReferralCommission.objects.filter(referral=referral, source_reference=purchase.payment_reference).exists():
        return  # already credited for this exact payment

    if not is_first_real_purchase:
        return  # a renewal / later purchase - never generates a commission

    already_has_commission = referral.commissions.exclude(status=ReferralCommission.Status.REVERSED).exists()
    if already_has_commission:
        return  # one-time only - this referral has already earned its commission

    amount_ngn = compute_commission_amount_ngn(purchase.amount_paid_kobo)
    if amount_ngn <= 0:
        return

    try:
        commission = ReferralCommission.objects.create(
            referral=referral,
            source_reference=purchase.payment_reference,
            subscription_purchase=purchase,
            amount_ngn=amount_ngn,
        )
    except IntegrityError:
        # Two near-simultaneous calls for the same payment (e.g. a client
        # verify call racing the charge.success webhook for the same
        # purchase) can both pass the .exists() check above before either
        # commits - the unique_together on (referral, source_reference) is
        # the real guarantee against double-crediting, this just means
        # "someone else already created it a moment ago," not a real
        # failure.
        logger.info('Referral commission for %s already created concurrently - skipping duplicate.', purchase.payment_reference)
        return

    attempt_payout(commission)
    return commission


def reverse_commissions_for_reference(source_reference, reason=''):
    """
    Called from apps.billing.services.mark_purchase_refunded when a
    subscription payment is refunded/reversed. Marks every (normally at
    most one) non-reversed commission tied to that exact payment as
    REVERSED - regardless of whether it was still PENDING or had already
    been PAID out - and NEVER deletes the row (spec \u00a78: "never delete
    historical financial records merely because a transaction was
    reversed"). A commission that had already been paid stays visible in
    Django Admin with status REVERSED and its original amount/payout
    details intact, which is the auditable record of "this was paid, then
    the underlying payment was refunded" - recovering the money from the
    referrer, if the business decides to, is a manual/support process this
    does not attempt to automate.
    """
    with transaction.atomic():
        commissions = list(
            ReferralCommission.objects.select_for_update()
            .filter(source_reference=source_reference).exclude(status=ReferralCommission.Status.REVERSED)
        )
        _reverse_locked(commissions, reason)


def _reverse_locked(commissions, reason):
    now = timezone.now()
    for commission in commissions:
        commission.status = ReferralCommission.Status.REVERSED
        commission.failure_reason = (reason or 'Source payment refunded/reversed.')[:255]
        commission.reversed_at = now
        commission.save(update_fields=['status', 'failure_reason', 'reversed_at', 'updated_at'])
        logger.info('Referral commission %s reversed: %s', commission.id, reason)


def attempt_payout(commission):
    """
    Tries to actually pay a PENDING/FAILED commission out via Paystack
    Transfer right now. Called both immediately after a commission is
    created (in case the referrer already has payout details on file) and
    from sweep_pending_payouts() (once they add payout details later, or
    as a periodic retry for a transient failure).

    Deliberately NOT gated on ReferralSettings.enabled: that flag stops
    NEW referrals/commissions from being created, it does not stop money
    already earned from being paid.

    Never raises - a payout attempt failing must never break the payment
    flow it was triggered from. Every outcome is recorded on the
    commission itself (status/failure_reason) so it's visible in Django
    Admin either way.

    Concurrency: this CLAIMS the commission (atomically flips it to
    PROCESSING under a row lock) before making the external Paystack call,
    and re-checks its status while holding that lock. Two calls for the
    SAME commission can otherwise both land here at once - e.g. the
    payout-attempt made right when a commission is first created racing a
    sweep_pending_payouts() triggered by the referrer saving their payout
    account a moment later - and without this claim step, both would see
    status PENDING, both would call Paystack, and BOTH transfers would go
    out for real: the reference sent to Paystack is freshly randomized on
    every call (see `reference` below), so Paystack's own idempotency
    can't catch a same-commission double-call the way payment_reference
    does for SubscriptionPurchase. Whichever call loses the race here
    returns immediately instead, before ever touching the network.
    """
    with transaction.atomic():
        locked = ReferralCommission.objects.select_for_update().get(pk=commission.pk)
        if locked.status not in (ReferralCommission.Status.PENDING, ReferralCommission.Status.FAILED):
            return  # already claimed (or resolved) by a concurrent call - nothing to do
        locked.status = ReferralCommission.Status.PROCESSING
        locked.failure_reason = ''
        locked.save(update_fields=['status', 'failure_reason', 'updated_at'])
    commission = locked

    referrer = commission.referral.referrer
    try:
        account = referrer.payout_account
    except PayoutAccount.DoesNotExist:
        # No payout account yet - revert the claim back to PENDING so
        # sweep_pending_payouts() can still find and retry it once they add
        # one, rather than leaving it stuck in PROCESSING forever.
        commission.status = ReferralCommission.Status.PENDING
        commission.save(update_fields=['status', 'updated_at'])
        return
    if not account.paystack_recipient_code:
        commission.status = ReferralCommission.Status.PENDING
        commission.save(update_fields=['status', 'updated_at'])
        return

    amount_kobo = int((commission.amount_ngn * 100).to_integral_value())
    reference = f'ref_{commission.id}_{uuid.uuid4().hex[:10]}'
    try:
        result = paystack.initiate_transfer(
            account.paystack_recipient_code, amount_kobo,
            reason='VendorIQ referral commission (initial subscription)',
            reference=reference,
        )
    except paystack.PaystackAmbiguousError as exc:
        # Timeout / connection reset / 5xx: Paystack may HAVE created the
        # transfer. Marking this FAILED (as any PaystackError used to be)
        # made the next sweep send a SECOND transfer under a fresh random
        # reference - a double payout. Leave it PROCESSING (which sweeps
        # never retry) and record the reference so support can look it up
        # in the Paystack dashboard; the transfer webhook resolves it
        # automatically if the transfer did go through.
        logger.error('Referral payout for commission %s has an UNKNOWN outcome (%s) - reference %s', commission.id, exc, reference)
        commission.status = ReferralCommission.Status.PROCESSING
        commission.failure_reason = f'Outcome unknown (network error). Check Paystack for reference {reference} before retrying.'[:255]
        commission.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return
    except paystack.PaystackError as exc:
        logger.error('Referral payout failed for commission %s: %s', commission.id, exc)
        commission.status = ReferralCommission.Status.FAILED
        commission.failure_reason = str(exc)[:255]
        commission.save(update_fields=['status', 'failure_reason', 'updated_at'])
        return

    transfer_status = (result or {}).get('status')
    commission.paystack_transfer_code = (result or {}).get('transfer_code', '')
    commission.failure_reason = ''
    if transfer_status == 'success':
        commission.status = ReferralCommission.Status.PAID
        commission.paid_at = timezone.now()
    elif transfer_status in ('otp', 'pending'):
        commission.status = ReferralCommission.Status.PROCESSING
        if transfer_status == 'otp':
            commission.failure_reason = 'Awaiting OTP confirmation on the Paystack dashboard (per-transfer OTP is still enabled on this Paystack account).'
    else:
        commission.status = ReferralCommission.Status.FAILED
        commission.failure_reason = f'Unexpected transfer status: {transfer_status}'
    commission.save(update_fields=['status', 'paystack_transfer_code', 'failure_reason', 'paid_at', 'updated_at'])


def sweep_pending_payouts(referrer):
    """
    Called right after a referrer sets up (or updates) their payout
    account - pays out anything earned earlier that's been sitting unpaid
    for lack of somewhere to send it, or because the last attempt failed.
    Deliberately excludes PROCESSING (already initiated, still resolving -
    retrying would risk a second transfer) and REVERSED (the underlying
    payment was refunded - this money is no longer owed).
    """
    commissions = ReferralCommission.objects.filter(
        referral__referrer=referrer,
        status__in=[ReferralCommission.Status.PENDING, ReferralCommission.Status.FAILED],
    )
    for commission in commissions:
        attempt_payout(commission)
