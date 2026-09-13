from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from .entitlements import get_subscription, start_trial, TrialAlreadyUsedError
from .serializers import SubscriptionSerializer
from .plans import PRO, FREE, public_plan_catalog, get_plan_config
from .models import SubscriptionStatus


def _resolve_billing_subject(request):
    """
    Figures out WHOSE subscription is relevant to this request.

    A Subscription belongs to a user, but plan/feature checks for anything
    happening inside a store are enforced against the STORE OWNER's
    subscription (apps/billing/entitlements.py) - the owner is who pays, so
    their plan is what the store's limits and Pro features actually are.
    The frontend used to always ask for `request.user`'s own subscription,
    which meant a staff member (whose own personal Subscription row is
    always Free - they never subscribe themselves) saw a stale/wrong "Free"
    plan even when the store they work at was Pro, and vice versa after a
    downgrade. Passing ?store_id= fixes that: this resolves to the OWNER of
    that store, for anyone who's actually a member of it (owner or staff).

    Returns (subject_user, viewer_is_owner, error_response_or_None).
    """
    store_id = request.query_params.get('store_id')
    if not store_id:
        # No store context (e.g. the very first load, before a store is
        # selected) - fall back to the caller's own subscription.
        return request.user, True, None

    from apps.stores.permissions import get_store_or_404, get_store_role
    try:
        store = get_store_or_404(store_id, request.user)
    except Exception:
        return None, None, Response({'error': 'Store not found.'}, status=status.HTTP_404_NOT_FOUND)

    role = get_store_role(store, request.user)
    if role is None:
        return None, None, Response({'error': 'You do not have access to this store.'}, status=status.HTTP_403_FORBIDDEN)

    return store.owner, (role == 'OWNER'), None


class SubscriptionView(APIView):
    """
    GET /api/billing/subscription/?store_id=<uuid> - the plan, status,
    billing period, live usage, and full plan catalog that's relevant to
    `store_id` (i.e. the STORE OWNER's subscription - see
    _resolve_billing_subject above), or the caller's own subscription if no
    store_id is given. Backs Settings > Subscription/Billing and any
    "X/Y products used" banner elsewhere in the app.

    `viewerIsOwner` in the response tells the frontend whether the caller
    can actually manage this subscription (upgrade/cancel) or is just a
    staff member viewing what plan their store is on.
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
    """GET /api/billing/plans/ - public plan catalog, no subscription state."""

    def get(self, request):
        return Response({'plans': public_plan_catalog()})


class UpgradeView(APIView):
    """
    POST /api/billing/upgrade/ - mock upgrade flow.

    No payment gateway exists in this project yet, so this activates Pro
    directly and records `provider='mock'`. Swap-in point for a real
    integration: a Paystack/Flutterwave checkout would redirect here (or to
    a webhook hitting the same `_activate_pro`) with a real
    `provider`/`provider_reference` once payment is confirmed, instead of
    activating unconditionally on request like this does. See the "Payment
    integration" section of the implementation notes for the exact swap.

    Locks in the CURRENT Pro price (get_plan_config(PRO)['price_ngn']) onto
    this subscription's price_ngn field at the moment of upgrade - a later
    admin price change (PricingSettings) then only affects new upgrades,
    not this one, which is what keeps MRR honest.
    """

    def post(self, request):
        plan = request.data.get('plan', PRO)
        if plan != PRO:
            return Response({'error': 'Only the Pro plan can be upgraded to.'}, status=status.HTTP_400_BAD_REQUEST)

        sub = get_subscription(request.user)
        now = timezone.now()
        plan_cfg = get_plan_config(PRO)
        sub.plan = PRO
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=plan_cfg['billing_period_days'])
        sub.cancel_at_period_end = False
        sub.provider = 'mock'
        sub.provider_reference = f'mock_{request.user.id}_{int(now.timestamp())}'
        # Lock in TODAY's price on this subscription - if the admin changes
        # PricingSettings later, that must only affect future upgrades, not
        # retroactively "charge" this subscriber more (or less) than what
        # they saw when they clicked Upgrade. See the price_ngn field
        # comment in models.py and compute_subscription_metrics() in
        # vendoriq/admin_dashboard.py, which sums this field for MRR
        # instead of count * current_price.
        sub.price_ngn = plan_cfg['price_ngn']
        sub.save()
        return Response(SubscriptionSerializer(sub).data, status=status.HTTP_200_OK)


class TrialView(APIView):
    """
    POST /api/billing/trial/start/ - starts a free Pro trial for the caller,
    lasting the CURRENT trial length (live-editable from Django Admin,
    Revenue & Billing > Free trial length - change it and every account
    currently mid-trial gets the new duration immediately, not just new
    trials; see Subscription.is_trial_active). One per account, ever - see
    entitlements.start_trial.
    """

    def post(self, request):
        try:
            sub = start_trial(request.user)
        except TrialAlreadyUsedError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(SubscriptionSerializer(sub).data)


class CancelSubscriptionView(APIView):
    """
    POST /api/billing/cancel/ - cancel a PAID Pro subscription. Access is
    kept until current_period_end (standard "you paid for this period,
    keep it" behavior); Subscription.maybe_expire() flips plan/status to
    Free/EXPIRED automatically once that date passes - see models.py. No
    data is deleted on either cancellation or eventual expiry: a
    store/product created while on Pro is untouched, it just can't be
    added to further past the Free limit until the user upgrades again
    (enforced in entitlements.py).

    Not for trials or complimentary grants - a trial has no payment to
    cancel (it simply ends on its own once its trial length is up), and a
    complimentary grant is revoked from the admin, not by the user.
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
