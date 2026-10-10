import hashlib
import hmac
import json
import logging
import re
import uuid
import requests
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from vendoriq import analytics
from .entitlements import get_subscription, start_trial, TrialNotAllowedError
from apps.authentication.verification import require_verified
from .serializers import SubscriptionSerializer
from .plans import PRO, FREE, BILLING_CYCLE_VALUES, public_plan_catalog
from .models import (
    SubscriptionStatus, Subscription, SubscriptionPurchase, CheckoutSession,
    get_current_plan_price, get_plan_pricing_catalog,
)
from .services import create_subscription_purchase

logger = logging.getLogger(__name__)

PAYSTACK_BASE_URL = 'https://api.paystack.co'

# Paystack references only ever contain letters, digits, '-', '.' and '='.
# The verify endpoint interpolates the client-supplied reference into a URL
# that carries our SECRET key, so anything else (slashes, '..', '?', '#')
# must never get that far.
REFERENCE_RE = re.compile(r'^[A-Za-z0-9=.\-]{1,100}$')


def _is_valid_amount(value):
    # bool is a subclass of int - `true` in JSON must not pass as 1 kobo.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _payment_matches_session(session, paid_kobo, currency):
    """
    The payment Paystack reports must be for AT LEAST what this checkout was
    priced at, in the same currency. (>= rather than ==: overpaying never
    hurts us, and the ledger records what was actually paid.)
    """
    if not _is_valid_amount(paid_kobo):
        return False
    if (currency or 'NGN') != session.currency:
        return False
    return paid_kobo >= session.amount_kobo


def _paystack_configured():
    """
    Both keys are required for a genuinely working real-payment setup -
    SECRET_KEY to talk to Paystack's REST API server-side, PUBLIC_KEY to
    open the checkout popup client-side (see PaystackInitializeView's
    response, which hands this straight to the frontend). Checking only
    SECRET_KEY here would let PaystackInitializeView start a REAL Paystack
    transaction, then hand the frontend an empty publicKey that
    PaystackPop.setup({key: '', ...}) can't do anything useful with - a
    transaction initialized, but a checkout popup that silently fails to
    render. Used consistently everywhere "is this environment in
    real-payment or demo mode" needs deciding, so the mock upgrade path
    and the real one can never disagree about which mode is active.
    """
    return bool(settings.PAYSTACK_SECRET_KEY and settings.PAYSTACK_PUBLIC_KEY)


def _resolve_billing_subject(request):
    """
    Figures out WHOSE subscription is relevant to this request.

    A Subscription belongs to a user, but plan/feature checks for anything
    happening inside a store are enforced against the STORE OWNER's
    subscription (apps/billing/entitlements.py) - the owner is who pays, so
    their plan is what the store's limits and Pro features actually are.
    Passing ?store_id= resolves to the OWNER of that store, for anyone
    who's actually a member of it (owner or staff).

    Returns (subject_user, viewer_is_owner, error_response_or_None).
    """
    store_id = request.query_params.get('store_id')
    if not store_id:
        return request.user, True, None

    from apps.stores.permissions import get_store_or_404, get_store_role
    try:
        store = get_store_or_404(store_id)
    except Exception:
        return None, None, Response({'error': 'Store not found.'}, status=status.HTTP_404_NOT_FOUND)

    role = get_store_role(store, request.user)
    if role is None:
        return None, None, Response({'error': 'You do not have access to this store.'}, status=status.HTTP_403_FORBIDDEN)

    return store.owner, (role == 'OWNER'), None


class SubscriptionView(APIView):
    """
    GET /api/billing/subscription/?store_id=<uuid> - the plan, status,
    billing cycle, live usage, and full pricing/plan catalog relevant to
    `store_id` (the STORE OWNER's subscription), or the caller's own
    subscription if no store_id is given.
    """

    def get(self, request):
        subject, viewer_is_owner, error = _resolve_billing_subject(request)
        if error:
            return error
        sub = get_subscription(subject)
        data = SubscriptionSerializer(sub).data
        data['viewerIsOwner'] = viewer_is_owner
        return Response(data)


class PlansView(APIView):
    """GET /api/billing/plans/ - public plan/feature catalog + live pricing for all three billing cycles, no subscription state required."""

    def get(self, request):
        return Response({
            'plans': public_plan_catalog(),
            'pricing': get_plan_pricing_catalog(),
        })


def _get_client_ip(request):
    from apps.authentication.models import get_client_ip
    return get_client_ip(request)


class UpgradeView(APIView):
    """
    POST /api/billing/upgrade/ {billing_cycle} - DEV-ONLY demo upgrade: grants
    Pro with provider='mock' and NO payment. Disabled unless
    settings.ALLOW_MOCK_UPGRADE is on (an explicit opt-in, e.g. in a local
    .env), and even then disabled whenever real Paystack payments are
    configured. Otherwise it goes through the exact same
    create_subscription_purchase() path as a real Paystack payment, so mock
    and real purchases can never disagree about what "purchased" means
    (expiry math, purchase records, renewal-vs-first-purchase bookkeeping).
    """

    def post(self, request):
        # A free-Pro endpoint must never be reachable by default - it is a
        # standing "skip payment" button for anyone who calls it directly.
        if not settings.ALLOW_MOCK_UPGRADE:
            return Response(
                {'error': 'Upgrading requires payment. Please use the checkout to pay.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if _paystack_configured():
            return Response(
                {'error': 'Payments are configured. Use the Paystack checkout to upgrade.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        billing_cycle = request.data.get('billing_cycle')
        if billing_cycle not in BILLING_CYCLE_VALUES:
            return Response({'error': 'A valid billing_cycle is required.'}, status=status.HTTP_400_BAD_REQUEST)

        price = get_current_plan_price(billing_cycle)
        now = timezone.now()
        reference = f'mock_{request.user.id}_{int(now.timestamp())}'
        purchase, _created = create_subscription_purchase(
            user=request.user,
            billing_cycle=billing_cycle,
            amount_paid_kobo=price['price_kobo'],
            currency=price['currency'],
            payment_provider='mock',
            payment_reference=reference,
            plan_price_id=price['id'],
        )
        sub = get_subscription(request.user)
        return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)


class PaystackInitializeView(APIView):
    """
    POST /api/billing/paystack/initialize/ {billing_cycle} - starts a real
    Paystack transaction for the caller purchasing/renewing Pro under the
    given billing cycle, and returns the authorization details the
    frontend needs to open Paystack's checkout.

    Amount is always the CURRENT live price for that cycle
    (get_current_plan_price) - NEVER trusted from the request body -
    converted to kobo. `billing_cycle` and `user_id` are embedded in
    Paystack's `metadata`, which Paystack echoes back verbatim on both the
    verify call and the charge.success webhook - that's how both of those
    later know what was actually being purchased without trusting the
    client again.
    """

    def post(self, request):
        if not _paystack_configured():
            missing = [
                name for name, value in (
                    ('PAYSTACK_SECRET_KEY', settings.PAYSTACK_SECRET_KEY),
                    ('PAYSTACK_PUBLIC_KEY', settings.PAYSTACK_PUBLIC_KEY),
                ) if not value
            ]
            # This is a SERVER CONFIGURATION problem, not a user error - make
            # it impossible to miss in the logs (it used to fail silently
            # with a generic 503, which is exactly what made "checkout says
            # 503" hard to diagnose).
            logger.error('Paystack checkout unavailable: missing environment variable(s): %s', ', '.join(missing))
            body = {
                'error': 'Payments are not available right now. Please try again later or contact support.',
                'code': 'payments_not_configured',
                # Only true in local dev with ALLOW_MOCK_UPGRADE=true -
                # tells the frontend it may offer the free demo upgrade.
                'mockUpgradeAvailable': bool(settings.ALLOW_MOCK_UPGRADE),
            }
            if settings.DEBUG:
                # Never shown in production - names the exact fix for whoever runs the server.
                body['error'] = f"Payments are not configured on the server: set {' and '.join(missing)} in your .env (Paystack dashboard > Settings > API Keys) and restart."
            return Response(body, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Paying requires a verified email and phone (see TrialView).
        require_verified(request.user)

        billing_cycle = request.data.get('billing_cycle')
        if billing_cycle not in BILLING_CYCLE_VALUES:
            return Response({'error': 'A valid billing_cycle is required (MONTHLY, SIX_MONTH, or ANNUAL).'}, status=status.HTTP_400_BAD_REQUEST)

        price = get_current_plan_price(billing_cycle)
        now = timezone.now()
        # Paystack's transaction reference field only allows -, ., = and
        # alphanumeric characters - NOT underscore (that's Transfers,
        # which are more permissive; Transactions are not - see
        # https://paystack.com/docs/api/transaction/ and the Transaction
        # Errors reference). billing_cycle values like 'SIX_MONTH' contain
        # an underscore too, so it isn't enough to just avoid adding new
        # ones - replace every underscore with a hyphen everywhere in the
        # reference. Getting this wrong means Paystack rejects the
        # /transaction/initialize call outright, so payments never work at
        # all regardless of how correctly the keys are configured.
        safe_cycle = billing_cycle.replace('_', '-')
        # The random suffix stops two checkouts started in the same second
        # (double-click, two tabs) from colliding on one reference.
        reference = f'viq-{request.user.id}-{safe_cycle}-{int(now.timestamp())}-{uuid.uuid4().hex[:8]}'

        # Server-side record of what this checkout is priced at - verify and
        # the webhook compare the real payment against THIS, never against
        # anything the browser (or Paystack metadata) claims. See
        # CheckoutSession's docstring.
        session = CheckoutSession.objects.create(
            reference=reference, user=request.user, billing_cycle=billing_cycle,
            amount_kobo=price['price_kobo'], currency=price['currency'], plan_price_id=price['id'],
        )

        try:
            response = requests.post(
                f'{PAYSTACK_BASE_URL}/transaction/initialize',
                headers={
                    'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}',
                    'Content-Type': 'application/json',
                },
                json={
                    'email': request.user.email,
                    'amount': price['price_kobo'],
                    'currency': price['currency'],
                    'reference': reference,
                    'metadata': {'user_id': str(request.user.id), 'plan': PRO, 'billing_cycle': billing_cycle},
                },
                timeout=15,
            )
        except requests.exceptions.RequestException:
            session.delete()
            logger.error('Paystack initialize request failed (network/timeout)', exc_info=True)
            return Response({'error': 'Could not reach the payment provider. Please try again shortly.'}, status=status.HTTP_502_BAD_GATEWAY)

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code != 200 or not data.get('status'):
            session.delete()
            logger.error('Paystack initialize returned %s: %s', response.status_code, response.text[:500])
            return Response({'error': data.get('message') or 'Could not start payment. Please try again.'}, status=status.HTTP_502_BAD_GATEWAY)

        payload = data['data']
        return Response({
            'authorizationUrl': payload['authorization_url'],
            'accessCode': payload['access_code'],
            'reference': payload['reference'],
            'amountKobo': price['price_kobo'],
            'billingCycle': billing_cycle,
            'publicKey': settings.PAYSTACK_PUBLIC_KEY,
        })


class PaystackVerifyView(APIView):
    """
    POST /api/billing/paystack/verify/ {reference} - called by the
    frontend right after Paystack's popup/redirect reports success.
    Re-verifies directly against Paystack's API (never trusts the
    frontend's word) before recording the purchase - this is the
    fast-path activation; PaystackChargeWebhookView below is the
    authoritative backup in case the user closes the tab before this call
    fires. Both funnel into the exact same idempotent
    create_subscription_purchase(), so whichever one runs first "wins" and
    the other becomes a no-op.
    """

    def post(self, request):
        reference = request.data.get('reference')
        if not isinstance(reference, str) or not REFERENCE_RE.match(reference):
            return Response({'error': 'A valid payment reference is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Paystack's verify endpoint confirms a reference is a genuinely
        # successful transaction WITHOUT caring which of our users it
        # belongs to, so the reference must be one WE issued to THIS user
        # (see CheckoutSession) - anyone could otherwise activate Pro by
        # verifying with any successful reference on our Paystack account.
        session = CheckoutSession.objects.filter(reference=reference).first()
        if session is None or session.user_id != request.user.id:
            return Response({'error': 'This payment reference does not belong to your account.'}, status=status.HTTP_403_FORBIDDEN)

        if not settings.PAYSTACK_SECRET_KEY:
            return Response({'error': 'Payments are not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            response = requests.get(
                f'{PAYSTACK_BASE_URL}/transaction/verify/{reference}',
                headers={'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}'},
                timeout=15,
            )
        except requests.exceptions.RequestException:
            logger.error('Paystack verify request failed (network/timeout)', exc_info=True)
            return Response({'error': 'Could not reach the payment provider. Please try again shortly.'}, status=status.HTTP_502_BAD_GATEWAY)

        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code != 200 or not data.get('status'):
            logger.error('Paystack verify returned %s: %s', response.status_code, response.text[:500])
            return Response({'error': data.get('message') or 'Could not verify payment.'}, status=status.HTTP_502_BAD_GATEWAY)

        payload = data.get('data') or {}
        if payload.get('status') != 'success':
            return Response({'error': f"Payment not successful (status: {payload.get('status')})."}, status=status.HTTP_400_BAD_REQUEST)

        if payload.get('reference') not in (None, reference):
            logger.error('Paystack verify for %s returned a different reference: %r', reference, payload.get('reference'))
            return Response({'error': 'Could not verify the payment.'}, status=status.HTTP_400_BAD_REQUEST)

        # What was ACTUALLY paid, per Paystack itself, checked against what
        # THIS checkout was priced at when it was created. The billing cycle
        # comes from our own session row, never from the metadata (which the
        # browser can set to anything - see CheckoutSession's docstring).
        amount_kobo_paid = payload.get('amount')
        if not _payment_matches_session(session, amount_kobo_paid, payload.get('currency')):
            logger.error(
                'Paystack verify for %s: paid %r %r but checkout was priced at %s %s - refusing to activate.',
                reference, amount_kobo_paid, payload.get('currency'), session.amount_kobo, session.currency,
            )
            return Response({'error': 'The amount paid does not match the plan price. Please contact support.'}, status=status.HTTP_400_BAD_REQUEST)

        purchase, _created = create_subscription_purchase(
            user=request.user,
            billing_cycle=session.billing_cycle,
            amount_paid_kobo=amount_kobo_paid,
            currency=session.currency,
            payment_provider='paystack',
            payment_reference=reference,
            plan_price_id=session.plan_price_id,
        )
        sub = get_subscription(request.user)
        return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)


class PaystackChargeWebhookView(APIView):
    """
    POST /api/billing/paystack-webhook/ - Paystack's server-to-server
    notification for CHARGE events (payments and refunds), separate from
    apps/referrals/views.py's PaystackTransferWebhookView (which only
    handles referral PAYOUT transfers). This is the authoritative,
    always-eventually-consistent path for activating a subscription: even
    if the user closes the browser tab before PaystackVerifyView's client
    call fires, this webhook still lands and activates it.

    Every request's signature is verified against PAYSTACK_SECRET_KEY
    before anything in the payload is trusted, exactly as Paystack
    documents: https://paystack.com/docs/payments/webhooks/
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    # Signed server-to-server calls from Paystack must never be rate limited:
    # the default anon throttle (30/min per IP) would answer a burst of
    # legitimate webhooks - which all come from a handful of Paystack IPs -
    # with 429s, and a paid customer would wait for a retry to get Pro.
    throttle_classes = []

    def post(self, request):
        signature = request.headers.get('x-paystack-signature', '')
        if not settings.PAYSTACK_SECRET_KEY or not signature:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), request.body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning('Paystack charge webhook signature mismatch - request discarded.')
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(request.body)
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        event = payload.get('event', '')
        data = payload.get('data') or {}
        if not isinstance(data, dict):
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            if event == 'charge.success':
                self._handle_charge_success(data)
            elif event in ('refund.processed',):
                self._handle_refund(data)
        except Exception:
            # An UNEXPECTED failure (DB blip, deploy in progress...) must
            # NOT be answered with 200: Paystack treats 200 as "delivered"
            # and never retries, so the customer would have paid and never
            # received Pro. A 5xx makes Paystack redeliver, and
            # create_subscription_purchase is idempotent per reference so a
            # retry is always safe. Expected/invalid payloads are handled
            # inside the handlers with a plain return (-> 200), never here.
            logger.error('Error handling Paystack charge webhook event=%s', event, exc_info=True)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(status=status.HTTP_200_OK)

    def _handle_charge_success(self, data):
        reference = data.get('reference')
        if not isinstance(reference, str) or not REFERENCE_RE.match(reference):
            logger.warning('Paystack charge.success webhook with missing/invalid reference: %r', reference)
            return
        if data.get('status') not in (None, 'success'):
            return

        # Only payments WE started are ours: this Paystack account may also
        # serve other products, and the metadata on a charge is
        # attacker-controlled (see CheckoutSession). The buyer, billing
        # cycle and expected price all come from our own session row.
        session = CheckoutSession.objects.select_related('user').filter(reference=reference).first()
        if session is None:
            logger.warning('Paystack charge.success for reference=%s has no checkout session - ignored (not one of our checkouts).', reference)
            return

        amount_kobo = data.get('amount')
        if not _payment_matches_session(session, amount_kobo, data.get('currency')):
            logger.error(
                'Paystack charge.success for %s: paid %r %r but checkout was priced at %s %s - NOT activating. Needs manual review.',
                reference, amount_kobo, data.get('currency'), session.amount_kobo, session.currency,
            )
            return

        create_subscription_purchase(
            user=session.user,
            billing_cycle=session.billing_cycle,
            amount_paid_kobo=amount_kobo,
            currency=session.currency,
            payment_provider='paystack',
            payment_reference=reference,
            plan_price_id=session.plan_price_id,
        )

    def _handle_refund(self, data):
        transaction_data = data.get('transaction') or {}
        reference = transaction_data.get('reference') or data.get('transaction_reference')
        if not reference:
            return
        try:
            purchase = SubscriptionPurchase.objects.get(payment_reference=reference)
        except SubscriptionPurchase.DoesNotExist:
            logger.warning('Paystack refund.processed webhook for unknown reference=%s', reference)
            return
        from .services import mark_purchase_refunded
        mark_purchase_refunded(purchase, reason='Refunded via Paystack')


class TrialView(APIView):
    """
    POST /api/billing/trial/start/ - starts a free Pro trial for the
    caller, lasting the CURRENT trial length. One per account, ever (plus
    a phone-number cross-account check) - see entitlements.start_trial.
    """

    def post(self, request):
        # The phone number is the anti-abuse key for the one-per-person
        # trial - it means nothing until the person has proved they own it.
        require_verified(request.user)
        ip = _get_client_ip(request)
        try:
            sub = start_trial(request.user, ip_address=ip)
        except TrialNotAllowedError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        analytics.capture(request.user, 'trial_started', set_props={'plan': 'PRO'})
        return Response(SubscriptionSerializer(sub).data)


class CancelSubscriptionView(APIView):
    """
    POST /api/billing/cancel/ - cancel a PAID Pro subscription. Access is
    kept until current_period_end; Subscription.maybe_expire() flips
    plan/status to Free/EXPIRED automatically once that date passes. No
    refund is issued and no historical SubscriptionPurchase is touched.
    """

    def post(self, request):
        sub = get_subscription(request.user)
        if sub.status == SubscriptionStatus.TRIAL:
            return Response(
                {'error': "Your trial doesn't need to be cancelled - it'll end on its own, and you can start using Free features again anytime."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if sub.is_complimentary:
            return Response({'error': 'This account has complimentary Pro access - contact support to change it.'}, status=status.HTTP_400_BAD_REQUEST)
        if sub.plan != PRO:
            return Response({'error': 'You are not on the Pro plan.'}, status=status.HTTP_400_BAD_REQUEST)
        sub.cancel_at_period_end = True
        sub.status = SubscriptionStatus.CANCELLED
        sub.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
        return Response(SubscriptionSerializer(sub).data)


class ResumeSubscriptionView(APIView):
    """POST /api/billing/resume/ - undo a pending cancellation, while still within the paid period."""

    def post(self, request):
        sub = get_subscription(request.user)
        if sub.plan != PRO or not sub.cancel_at_period_end:
            return Response({'error': 'No pending cancellation to resume.'}, status=status.HTTP_400_BAD_REQUEST)
        sub.cancel_at_period_end = False
        sub.status = SubscriptionStatus.ACTIVE
        sub.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
        return Response(SubscriptionSerializer(sub).data)
