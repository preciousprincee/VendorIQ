"""
Reusable subscription/entitlement service. Every "can this user do X"
question in the app - across stores, products, staff, insights, invoices,
exports, and the AI assistant - goes through one of the functions below
instead of a one-off `if store.owner.subscription.plan == 'PRO'` scattered
through view code. That's what lets a future plan/limit/feature change stay
a change to plans.py + this file, not a hunt through a dozen views.

Ownership rule used throughout: a Subscription belongs to a *user*, but
every store-scoped limit (products, staff) is enforced against the STORE
OWNER's subscription, not the acting staff member's - the owner is who
pays, so their plan is what the store's limits are. `get_subscription`
accepts any user (owner or staff); callers pass `store.owner` for
store-scoped checks and `request.user` for account-level ones (creating a
new store).
"""
from django.db.models import Count
from django.utils import timezone
from .models import Subscription, SubscriptionStatus
from .plans import FREE, PRO, get_plan_config, plan_limit, plan_has_feature
from .exceptions import UpgradeRequired


def get_subscription(user):
    """
    Fetch-or-create a user's Subscription, lazily. New/existing users alike
    get a Free subscription row the first time anything asks about their
    plan - no signal, no data migration for pre-existing accounts needed.
    Always call this (not `user.subscription` directly) since it also
    applies any pending Pro->Free expiry before returning.
    """
    sub, _created = Subscription.objects.get_or_create(user=user)
    return sub.maybe_expire()


def get_effective_plan(user):
    return get_subscription(user).effective_plan


class TrialAlreadyUsedError(Exception):
    """Raised by start_trial() when a user tries to start a second trial - see that function."""


def start_trial(user):
    """
    Starts a free Pro trial for `user`, lasting the current trial length
    (apps/billing/models.py::get_trial_period_days() - live-editable from
    Django Admin, not a redeploy-only env var) from right now. One trial per
    account, ever - `has_used_trial` blocks a second one (a user cancelling
    and re-starting a trial to get indefinite free Pro would otherwise be
    trivial). An admin can reset that flag from Django admin for a genuine
    support case - see apps/billing/admin.py's "Reset trial eligibility"
    action.

    Does nothing to an account that's already on Pro (paid or comped) -
    call sites should check get_effective_plan(user) == FREE first if they
    want to show/hide a "start trial" button rather than relying on this
    raising for that case too.
    """
    sub = get_subscription(user)
    if sub.has_used_trial:
        raise TrialAlreadyUsedError("You've already used your free trial.")
    now = timezone.now()
    sub.plan = PRO
    sub.status = SubscriptionStatus.TRIAL
    sub.trial_started_at = now
    sub.has_used_trial = True
    sub.is_complimentary = False
    sub.cancel_at_period_end = False
    sub.current_period_start = now
    sub.current_period_end = None  # trial expiry is computed from trial_started_at, not this
    sub.price_ngn = 0  # trialing, not paying - must never count toward MRR
    sub.provider = ''
    sub.save()
    return sub


def has_feature(user, feature_key):
    return plan_has_feature(get_effective_plan(user), feature_key)


def require_feature(user, feature_key, *, title=None, description=None):
    """
    Raise UpgradeRequired unless `user`'s (owner's) plan includes
    `feature_key`. `description` is the upsell copy shown in the upgrade
    modal - keep it benefit-focused ("see which products drive your
    profit"), not just a repeat of the feature name.
    """
    if has_feature(user, feature_key):
        return
    from .plans import FEATURES
    label = FEATURES.get(feature_key, 'This feature')
    raise UpgradeRequired(
        description or f'{label} is a Pro feature.',
        code='UPGRADE_REQUIRED',
        feature=feature_key,
        title=title or f'Unlock {label}',
    )


def require_within_limit(user, limit_key, current_count, *, feature=None, title=None, message=None):
    """
    Raise UpgradeRequired if adding one more of whatever `limit_key`
    tracks (a store, a product, a staff member) would exceed the owner's
    plan limit. `current_count` is the count BEFORE the new item, so this
    should be called as `require_within_limit(..., current_count=qs.count())`
    right before the create.
    """
    limit = plan_limit(get_effective_plan(user), limit_key)
    if limit is None:  # unlimited on this plan
        return
    if current_count >= limit:
        raise UpgradeRequired(
            message or f"You've reached the {limit} limit on the Free plan.",
            code='LIMIT_REACHED',
            feature=feature,
            title='Upgrade to Pro',
            limit=limit,
            current=current_count,
        )


# --- Specific, named checks -------------------------------------------------
# Thin wrappers around require_within_limit/require_feature with the exact
# copy from the product spec, kept together so every call site reads the
# same message rather than each view inventing its own wording.

def check_can_add_store(user):
    from apps.stores.models import Store
    current = Store.objects.filter(owner=user).count()
    require_within_limit(
        user, 'max_stores', current,
        message="You've reached the 1-store limit on the Free plan. Upgrade to Pro for multiple stores.",
    )


def check_can_add_product(store):
    from apps.products.models import Product
    current = Product.objects.filter(store=store).count()
    limit = plan_limit(get_effective_plan(store.owner), 'max_products_per_store')
    require_within_limit(
        store.owner, 'max_products_per_store', current,
        message=(
            f"You've reached the {limit}-product limit on the Free plan. Upgrade to Pro for unlimited products."
            if limit is not None else None
        ),
    )


def check_can_add_staff(store):
    from apps.stores.models import Staff
    # +1 for the owner, who is always a "user" of the store but has no Staff row.
    current = Staff.objects.filter(store=store).count() + 1
    require_within_limit(
        store.owner, 'max_users_per_store', current,
        message="The Free plan is limited to 1 user per store. Upgrade to Pro for staff accounts.",
    )


def require_invoicing(owner):
    require_feature(
        owner, 'invoicing', title='Unlock Invoicing',
        description='Create and send professional invoices to your customers, and track which ones are paid.',
    )


def require_ai_assistant(owner):
    require_feature(
        owner, 'ai_assistant', title='Unlock the AI Business Assistant',
        description='Ask questions about your sales, profit, and stock in plain language and get instant answers.',
    )


def require_data_export(owner):
    require_feature(
        owner, 'data_export', title='Unlock CSV Exports',
        description='Download your full bookkeeping records as a CSV - handy for loan applications and accountants.',
    )


def require_advanced_profit_analytics(owner):
    require_feature(
        owner, 'advanced_profit_analytics', title='Unlock Advanced Profit Analytics',
        description='See true store profitability after overhead, broken down by today, this month, and all time.',
    )


def clamp_trend_days(owner, requested_days):
    """
    The Insights trend chart isn't hard-gated behind Pro (it's core to
    "basic reports"/the dashboard sparkline) - Free just can't look back as
    far. Silently clamping (rather than erroring) keeps the endpoint useful
    for Free users while still making the Pro upsell obvious in the UI
    (see InsightsPage disabling the 30/90-day options for Free).
    """
    max_days = plan_limit(get_effective_plan(owner), 'max_trend_history_days')
    if max_days is None:
        return requested_days
    return min(requested_days, max_days)


# --- Usage summary (for the Subscription/Billing page & dashboard banners) --

def get_usage(user):
    """
    Current usage against each Free-plan limit, for the owner `user`.
    Powers "what you have left" on the Subscription page and the
    near-limit banners on Products/Staff/Stores. Meaningless for a Pro
    user's own limits (they're unlimited) but still returned so the UI can
    show raw counts ("128 products") without a Pro/Free branch.
    """
    from apps.stores.models import Store, Staff
    from apps.products.models import Product

    stores = Store.objects.filter(owner=user)
    store_count = stores.count()

    # Per-store product/staff counts - a dict keyed by store id so the
    # frontend can show "72/100 products in Main Store" for whichever store
    # is active, not just a single global number that wouldn't make sense
    # once a Pro user has several stores with different catalog sizes.
    products_by_store = {
        row['store']: row['n']
        for row in Product.objects.filter(store__in=stores).values('store').annotate(n=Count('id'))
    }
    staff_by_store = {
        row['store']: row['n'] + 1  # +1 for the owner
        for row in Staff.objects.filter(store__in=stores).values('store').annotate(n=Count('id'))
    }
    for store in stores:
        products_by_store.setdefault(store.id, 0)
        staff_by_store.setdefault(store.id, 1)

    return {
        'stores': store_count,
        'productsByStore': {str(k): v for k, v in products_by_store.items()},
        'staffByStore': {str(k): v for k, v in staff_by_store.items()},
    }
