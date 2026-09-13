"""
Central plan configuration for VendorIQ's Free/Pro subscription model.

This is the ONE place plan pricing, limits, and feature access are defined.
Nothing else in the codebase should hardcode a price, a limit like "100
products", or a feature name - it should read from PLANS instead. That's
what makes "change the Pro price" or "add a Plus tier later" a one-file
change instead of a grep-and-replace across the whole app.

UNLIMITED is represented as None throughout (not 0, not -1, not a huge
int) - `limit is None` is an unambiguous, greppable way to ask "is this
capped at all?" in entitlements.py and every view that checks a limit.
"""
import os

# Use `None` for "unlimited". Never hardcode these numbers anywhere else -
# import PLANS (or the helpers in entitlements.py) instead.

FREE = 'FREE'
PRO = 'PRO'

PLAN_CHOICES = [
    (FREE, 'Free'),
    (PRO, 'Pro'),
]

# Feature flags. Every Pro-gated capability in the product gets a key here -
# apps/billing/entitlements.py::has_feature() and the FeatureGate component
# on the frontend both key off these exact strings, so treat them as a
# stable contract between backend and frontend, not free-form text.
FEATURES = {
    'multiple_stores': 'Multiple stores',
    'multiple_staff': 'Multiple staff accounts',
    'advanced_sales_analytics': 'Advanced sales analytics',
    'advanced_profit_analytics': 'Advanced profit analytics',
    'advanced_expense_analytics': 'Advanced expense analytics',
    'detailed_reports': 'Detailed reports',
    'data_export': 'CSV / PDF exports',
    'invoicing': 'Invoicing',
    'customer_management': 'Customer management',
    'cloud_backup': 'Cloud backup',
    'advanced_low_stock_insights': 'Advanced low-stock insights',
    'automated_summaries': 'Automated business summaries',
    'ai_assistant': 'AI business assistant',
    'advanced_dashboard': 'Advanced dashboard insights',
    'long_term_history': 'Longer historical data & analytics',
}

# Seed value only, used the FIRST time PricingSettings is ever read (see
# apps/billing/models.py::get_pro_price_ngn) to create that row. After
# that, the ACTUAL price lives in the database and is changed from Django
# Admin (Revenue & Billing > Pro plan price), not here - takes effect
# immediately, no redeploy. Code elsewhere should call
# get_plan_config(PRO)['price_ngn'] (which calls get_pro_price_ngn()
# internally), not this constant directly - this is only ever read once,
# at seed time.
PRO_PRICE_NGN = int(os.getenv('PRO_PRICE_NGN', '5000'))

# Seed value only, used the FIRST time TrialSettings is ever read (see
# apps/billing/models.py::TrialSettings) to create that row. After that,
# the ACTUAL trial length lives in the database and is changed from Django
# Admin (Revenue & Billing > Free trial length), not here - unlike
# PRO_PRICE_NGN, the trial length needs to be editable without a redeploy,
# and changing it must retroactively affect everyone currently mid-trial,
# not just future signups. See TrialSettings.get_duration_days() and
# Subscription.is_trial_active for exactly how that works. Code elsewhere
# should call get_trial_period_days() (apps/billing/models.py), not this
# constant directly - this is only ever read once, at seed time.
TRIAL_PERIOD_DAYS = int(os.getenv('TRIAL_PERIOD_DAYS', '14'))

PLANS = {
    FREE: {
        'name': 'Free',
        'price_ngn': 0,
        'billing_period_days': None,  # Free never expires/renews
        'limits': {
            'max_stores': 1,
            'max_products_per_store': 100,
            'max_users_per_store': 1,  # owner only, no staff
            'max_trend_history_days': 14,  # "limited historical analytics"
        },
        'features': {key: False for key in FEATURES},
        'tagline': 'Everything a solo shop needs to get started.',
        'includes': [
            'Product & inventory management',
            'Sales & expense recording',
            'Low-stock alerts',
            'Daily sales summary & basic profit tracking',
            '1 store, 1 user',
            'Up to 100 products',
            'Basic dashboard & reports',
        ],
    },
    PRO: {
        'name': 'Pro',
        'price_ngn': PRO_PRICE_NGN,
        'billing_period_days': 30,
        'limits': {
            'max_stores': None,
            'max_products_per_store': None,
            'max_users_per_store': None,
            'max_trend_history_days': 365,
        },
        'features': {key: True for key in FEATURES},
        'tagline': 'Everything you need to run and grow multiple stores.',
        'includes': [
            'Unlimited products & stores',
            'Multiple staff accounts',
            'Advanced sales, profit & expense analytics',
            'Detailed reports + CSV/PDF exports',
            'Invoicing & customer management',
            'Cloud backup',
            'AI business assistant',
            'Automated business summaries',
            'Longer historical data',
        ],
    },
}


def get_plan_config(plan):
    cfg = PLANS.get(plan, PLANS[FREE])
    if plan == PRO:
        # Live, admin-editable price (Django Admin > Revenue & Billing >
        # Pro plan price) - deferred import since models.py imports
        # FREE/PRO/PLAN_CHOICES/PRO_PRICE_NGN from this module at load
        # time, so importing it back at module level here would be
        # circular. Returns a NEW dict rather than mutating the shared
        # PLANS[PRO] dict, which every caller holds a reference to.
        from .models import get_pro_price_ngn
        cfg = {**cfg, 'price_ngn': get_pro_price_ngn()}
    return cfg


def plan_limit(plan, limit_key):
    return get_plan_config(plan)['limits'].get(limit_key)


def plan_has_feature(plan, feature_key):
    return get_plan_config(plan)['features'].get(feature_key, False)


def public_plan_catalog():
    """
    Shape returned by GET /api/billing/plans/ and embedded in the
    subscription payload - everything the Settings > Subscription page and
    the upgrade modal need to render the Free/Pro comparison, without the
    frontend hardcoding a second copy of prices/limits/features. Goes
    through get_plan_config() per plan (not the raw PLANS dict directly) so
    Pro's price is always the current live value, not whatever was baked
    in at process startup.
    """
    catalog = []
    for code in PLANS.keys():
        cfg = get_plan_config(code)
        catalog.append({
            'code': code,
            'name': cfg['name'],
            'priceNgn': cfg['price_ngn'],
            'billingPeriodDays': cfg['billing_period_days'],
            'tagline': cfg['tagline'],
            'includes': cfg['includes'],
            'limits': {
                'maxStores': cfg['limits']['max_stores'],
                'maxProductsPerStore': cfg['limits']['max_products_per_store'],
                'maxUsersPerStore': cfg['limits']['max_users_per_store'],
                'maxTrendHistoryDays': cfg['limits']['max_trend_history_days'],
            },
            'features': cfg['features'],
        })
    return catalog
