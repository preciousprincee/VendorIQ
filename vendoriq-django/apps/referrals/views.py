import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from . import paystack
from .models import PayoutAccount, Referral, ReferralCommission, get_referral_settings
from .serializers import CommissionSerializer, PayoutAccountSerializer, SetPayoutAccountSerializer
from .services import sweep_pending_payouts

logger = logging.getLogger(__name__)

BANKS_CACHE_KEY = 'referrals:banks:v2'  # v2: full paginated list, {name, code} only


def get_cached_banks():
    """
    Shared by BanksListView and PayoutAccountView below - both need the
    same bank code->name lookup, and both must FETCH fresh from Paystack
    on a cache miss rather than silently proceeding with an empty list.
    PayoutAccountView used to do the latter: if this cache had expired or
    was simply never warmed (a fresh deploy, or a client that calls
    POST /payout-account/ without ever calling GET /banks/ first), the
    account got saved with its raw bank_code ("058") standing in for the
    bank's actual name - wrong, and confusing in Admin/on the Referrals
    page. Always resolving properly here (fetching on a miss, same as the
    list endpoint) closes that gap.
    """
    banks = cache.get(BANKS_CACHE_KEY)
    if banks is None:
        banks = paystack.list_banks()  # raises PaystackError on failure - let callers handle it
        cache.set(BANKS_CACHE_KEY, banks, 60 * 60 * 24)
    return banks


class ReferralStatusView(APIView):
    """
    GET /api/referrals/status/ - public, unauthenticated. Exists solely so
    the registration page (which nobody is logged into yet) can decide
    whether to show its "referral code" field at all, and what terms to
    show next to it, without exposing anything account-specific. Contrast
    with ReferralSummaryView below, which is the authenticated, per-user
    version of this.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        settings_ = get_referral_settings()
        return Response({
            'enabled': settings_['enabled'],
            'commissionPercent': settings_['commission_percent'],
        })


class ReferralSummaryView(APIView):
    """
    GET /api/referrals/summary/ - everything the Referrals page needs in
    one call: the caller's own code/link, program terms, who they've
    referred, and their earnings broken down by status.
    """

    def get(self, request):
        settings_ = get_referral_settings()
        referrals = Referral.objects.filter(referrer=request.user).select_related('referred_user').prefetch_related('commissions')

        referred = []
        for r in referrals:
            commissions = [c for c in r.commissions.all() if c.status != ReferralCommission.Status.REVERSED]
            live_commission = commissions[0] if commissions else None
            referred.append({
                'name': r.referred_user.name,
                'email': r.referred_user.email,
                'joinedAt': r.created_at,
                # The referral program pays once, from the referred user's
                # FIRST successful paid subscription - not a recurring
                # monthly credit. commissionStatus is None until they've
                # made a paid purchase (a trial alone never earns one).
                'commissionStatus': live_commission.status if live_commission else None,
                'totalEarnedNgn': sum((c.amount_ngn for c in commissions if c.status == ReferralCommission.Status.PAID), 0),
                'totalPendingNgn': sum((c.amount_ngn for c in commissions if c.status in (ReferralCommission.Status.PENDING, ReferralCommission.Status.PROCESSING)), 0),
            })

        totals = ReferralCommission.objects.filter(referral__referrer=request.user).aggregate(
            paid=Sum('amount_ngn', filter=Q(status=ReferralCommission.Status.PAID)),
            pending=Sum('amount_ngn', filter=Q(status__in=[ReferralCommission.Status.PENDING, ReferralCommission.Status.PROCESSING])),
        )

        try:
            payout_account = PayoutAccountSerializer(request.user.payout_account).data
        except PayoutAccount.DoesNotExist:
            payout_account = None

        return Response({
            # A user's phone number IS their referral code, so someone with
            # no (valid) phone yet has no code - the frontend shows an
            # "add your phone number" prompt instead of a blank code.
            'referralCode': request.user.referral_code or '',
            'referralPath': f'/register?ref={request.user.referral_code}' if request.user.referral_code else '',
            'needsPhone': not request.user.referral_code,
            'enabled': settings_['enabled'],
            'commissionPercent': settings_['commission_percent'],
            'referredUsers': referred,
            'totalPaidNgn': totals['paid'] or 0,
            'totalPendingNgn': totals['pending'] or 0,
            'payoutAccount': payout_account,
        })


class RecentCommissionsView(APIView):
    """GET /api/referrals/commissions/ - a flat, newest-first log of every commission this user has earned, for a simple activity list on the Referrals page."""

    def get(self, request):
        commissions = ReferralCommission.objects.filter(referral__referrer=request.user).select_related('referral__referred_user')[:100]
        return Response(CommissionSerializer(commissions, many=True).data)


class BanksListView(APIView):
    """GET /api/referrals/banks/ - Nigerian bank list for the payout-account form's dropdown. Cached for a day; Paystack's bank list changes rarely."""

    def get(self, request):
        try:
            banks = get_cached_banks()
        except paystack.PaystackError as exc:
            if not settings.PAYSTACK_SECRET_KEY:
                # Server misconfiguration, not a Paystack outage - say so in
                # the logs (and, in dev only, in the response).
                logger.error('Bank list unavailable: PAYSTACK_SECRET_KEY is not set on the server.')
                detail = 'Bank list unavailable: set PAYSTACK_SECRET_KEY in your .env and restart the server.' if settings.DEBUG else 'The bank list is unavailable right now. Please try again later.'
                return Response({'error': detail, 'code': 'payments_not_configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response({'error': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(banks)


class ResolveAccountView(APIView):
    """
    POST /api/referrals/payout-account/resolve/ {bank_code, account_number}
    - preview-only: confirms the account is real and returns its registered
    name, WITHOUT saving anything, so the frontend can show "Pay out to:
    <verified name>" and let the person confirm before committing.
    """

    def post(self, request):
        serializer = SetPayoutAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = paystack.resolve_account(serializer.validated_data['account_number'], serializer.validated_data['bank_code'])
        except paystack.PaystackError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'accountName': result['account_name']})


class PayoutAccountView(APIView):
    """
    GET returns the caller's saved payout account (404 if none yet). POST
    verifies the given account with Paystack, registers it as a transfer
    recipient, saves it, and immediately sweeps any commissions that were
    sitting PENDING for lack of somewhere to pay them out to.
    """

    def get(self, request):
        try:
            return Response(PayoutAccountSerializer(request.user.payout_account).data)
        except PayoutAccount.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

    def post(self, request):
        serializer = SetPayoutAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bank_code = serializer.validated_data['bank_code']
        account_number = serializer.validated_data['account_number']

        try:
            resolved = paystack.resolve_account(account_number, bank_code)
            account_name = resolved['account_name']
            recipient = paystack.create_transfer_recipient(account_name, account_number, bank_code)
            banks = get_cached_banks()
        except paystack.PaystackError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        bank_name = next((b['name'] for b in banks if b['code'] == bank_code), bank_code)

        account, _created = PayoutAccount.objects.update_or_create(
            user=request.user,
            defaults={
                'bank_code': bank_code, 'bank_name': bank_name, 'account_number': account_number,
                'account_name': account_name, 'paystack_recipient_code': recipient['recipient_code'],
            },
        )
        sweep_pending_payouts(request.user)
        return Response(PayoutAccountSerializer(account).data, status=status.HTTP_200_OK)


class PaystackTransferWebhookView(APIView):
    """
    POST /api/referrals/paystack-webhook/ - Paystack calls this when a
    transfer's status changes (transfer.success/failed/reversed). Needed
    because initiate_transfer()'s immediate response is only the STARTING
    status - on a live account with per-transfer OTP, or just generally,
    the final outcome often only arrives here, asynchronously.

    Unauthenticated (Paystack can't send your JWT), but every request's
    signature is verified against PAYSTACK_SECRET_KEY before anything in
    the payload is trusted - see verify below. This is the same mechanism
    Paystack documents for all webhooks: https://paystack.com/docs/payments/webhooks/
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    # Signed server-to-server calls; the per-IP anon throttle would 429 a
    # burst of legitimate transfer events from Paystack's few IPs.
    throttle_classes = []

    def post(self, request):
        signature = request.headers.get('x-paystack-signature', '')
        if not settings.PAYSTACK_SECRET_KEY or not signature:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), request.body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning('Paystack webhook signature mismatch - request discarded.')
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(request.body)
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(payload, dict) or not isinstance(payload.get('data') or {}, dict):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        event = payload.get('event', '')
        data = payload.get('data') or {}
        transfer_code = data.get('transfer_code') or ''
        reference = data.get('reference') or ''

        if event in ('transfer.success', 'transfer.failed', 'transfer.reversed') and (transfer_code or reference):
            with transaction.atomic():
                # .filter().first() rather than .get(): transfer_code isn't
                # DB-unique (blank for every not-yet-attempted commission).
                # Falls back to our own reference (ref_<commission id>_...) for
                # a transfer whose creation response we never received (see
                # PaystackAmbiguousError) and so never stored a code for.
                commission = None
                if transfer_code:
                    commission = ReferralCommission.objects.select_for_update().filter(paystack_transfer_code=transfer_code).order_by('-created_at').first()
                if commission is None and isinstance(reference, str) and reference.startswith('ref_'):
                    try:
                        commission = ReferralCommission.objects.select_for_update().filter(pk=reference.split('_')[1]).first()
                    except (ValueError, ValidationError, IndexError):
                        commission = None
                if commission is None:
                    logger.warning('Paystack webhook for unknown transfer_code=%s reference=%s', transfer_code, reference)
                    return Response(status=status.HTTP_200_OK)  # 200 so Paystack doesn't keep retrying a transfer that isn't ours

                Status = ReferralCommission.Status
                if transfer_code and not commission.paystack_transfer_code:
                    commission.paystack_transfer_code = transfer_code

                if commission.status == Status.REVERSED:
                    # The underlying payment was refunded and the commission
                    # reversed. A late transfer event must NOT flip it back to
                    # PAID (hiding a payout that needs recovering) or to
                    # FAILED (which sweep_pending_payouts would then PAY OUT).
                    logger.warning('Transfer event %s for already-REVERSED commission %s (transfer_code=%s) - left REVERSED; needs manual review.', event, commission.id, transfer_code)
                    if event == 'transfer.success' and not commission.paid_at:
                        commission.paid_at = timezone.now()
                    commission.save(update_fields=['paystack_transfer_code', 'paid_at', 'updated_at'])
                    return Response(status=status.HTTP_200_OK)

                if event == 'transfer.success':
                    commission.status = Status.PAID
                    commission.paid_at = timezone.now()
                    commission.failure_reason = ''
                elif event == 'transfer.failed' and commission.status == Status.PAID:
                    # Out-of-order/duplicate delivery: a "failed" for a
                    # transfer we already know succeeded must not downgrade it
                    # (a FAILED commission is re-paid by the next sweep).
                    # A genuine later reversal arrives as transfer.reversed.
                    logger.warning('Ignoring transfer.failed for already-PAID commission %s.', commission.id)
                    return Response(status=status.HTTP_200_OK)
                else:
                    commission.status = Status.FAILED
                    commission.failure_reason = (data.get('reason') or event)[:255]
                commission.save(update_fields=['status', 'paid_at', 'failure_reason', 'paystack_transfer_code', 'updated_at'])

        return Response(status=status.HTTP_200_OK)
