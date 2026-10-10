"""
Central plan configuration for VendorIQ's Free/Pro subscription model.

This is the ONE place plan features and billing-cycle metadata are
defined. Nothing else in the codebase should hardcode a price, a limit
like "100 products", or a feature name - it should read from PLANS /
BILLING_CYCLE_* instead. That's what makes "add a Plus tier later" a
one-file change instead of a grep-and-replace across the whole app.

Pricing itself (the actual Naira amount charged for each billing cycle)
is NOT hardcoded here - it lives in the database (apps.billing.models.PlanPrice)
so an administrator can change it without a redeploy, and so every price
change is versioned rather than mutating a constant in code. The values
below are SEED values only, used the first time PlanPrice is read for a
given cycle (see apps.billing.models.get_current_plan_price). Code that
needs the live price should call get_current_plan_price()/
get_plan_pricing_catalog() in models.py, never PRICE_SEED_KOBO directly.

UNLIMITED is represented as None throughout (not 0, not -1, not a huge
int) - `limit is None` is an unambiguous, greppable way to ask "is this
capped at all?" in entitlements.py and every view that checks a limit.
"""
import os

FREE = 'FREE'
PRO = 'PRO'

PLAN_CHOICES = [
    (FREE, 'Free'),
    (PRO, 'Pro'),
]

# --- Billing cycles ------------------------------------------------------
# VendorIQ Pro is sold in three billing cycles at launch. Each cycle is
# just "how many months of Pro access does one successful payment buy" -
# the feature set is identical across all three (see PLANS[PRO] below);
# only price and billing period differ. Adding a new cycle later (e.g. a
# quarterly plan) means adding one entry to each dict below and seeding a
# PlanPrice for it - nothing else in this module needs to change.
MONTHLY = 'MONTHLY'
SIX_MONTH = 'SIX_MONTH'
ANNUAL = 'ANNUAL'

BILLING_CYCLE_CHOICES = [
    (MONTHLY, '1 Month'),
    (SIX_MONTH, '6 Months'),
    (ANNUAL, '1 Year'),
]
BILLING_CYCLE_VALUES = {MONTHLY, SIX_MONTH, ANNUAL}

# Ordered for display purposes (pricing page, admin dropdowns).
BILLING_CYCLE_ORDER = [MONTHLY, SIX_MONTH, ANNUAL]

# How many calendar months one successful purchase of this cycle buys.
# Used for calendar-correct expiry-date math (apps.billing.services.add_months)
# rather than a fixed day count, so "1 year" always means "the same date
# next year", not "365 days" (which silently drifts across leap years).
BILLING_CYCLE_MONTHS = {
    MONTHLY: 1,
    SIX_MONTH: 6,
    ANNUAL: 12,
}

BILLING_CYCLE_LABELS = {
    MONTHLY: '1 Month',
    SIX_MONTH: '6 Months',
    ANNUAL: '1 Year',
}

# Seed prices in kobo (1 Naira = 100 kobo) - integer minor units, never a
# float. These are ONLY used the very first time a PlanPrice row is
# created for a cycle (see apps.billing.models.get_current_plan_price).
# After that, the live price lives in the database and is changed from
# Django Admin (Revenue & Billing > Plan prices) by adding a NEW PlanPrice
# version - never by editing this constant or an existing price row.
PRICE_SEED_KOBO = {
    MONTHLY: int(os.getenv('PRICE_MONTHLY_KOBO', '500000')),       # \u20a65,000
    SIX_MONTH: int(os.getenv('PRICE_SIX_MONTH_KOBO', '1500000')),  # \u20a615,000
    ANNUAL: int(os.getenv('PRICE_ANNUAL_KOBO', '2400000')),        # \u20a624,000
}

# Seed value only, used the FIRST time TrialSettings is ever read (see
# apps/billing/models.py::TrialSettings) to create that row. After that,
# the ACTUAL trial length lives in the database and is changed from Django
# Admin (Revenue & Billing > Free trial length), not here. Code elsewhere
# should call get_trial_period_days() (apps/billing/models.py), not this
# constant directly.
TRIAL_PERIOD_DAYS = int(os.getenv('TRIAL_PERIOD_DAYS', '30'))

# Feature flags. Every Pro-gated capability in the product gets a key here -
# apps/billing/entitlements.py::has_feature() and the FeatureGate component
# on the frontend both key off these exact strings, so treat them as a
# stable contract between backend and frontend, not free-form text.
# Identical across all three billing cycles - a Pro subscriber gets the
# same features whether they paid monthly, 6-monthly, or annually; only
# price and renewal cadence differ.
FEATURES = {
    'multiple_stores': 'Multiple stores',
    'multiple_staff': 'Multiple staff accounts',
    'advanced_sales_analytics': 'Advanced sales analytics',
    'advanced_profit_analytics': 'Advanced profit analytics',
    'advanced_expense_analytics': 'Advanced expense analytics',
    'detailed_reports': 'Detailed reports',
    'data_export': 'CSV / PDF exports',
    'invoicing': 'Invoicing',
    'customer_management': 'Customer management & credit sales',
    'cloud_backup': 'Cloud backup (full data download)',
    'advanced_low_stock_insights': 'Advanced low-stock insights',
    'automated_summaries': 'Automated business summaries',
    'ai_assistant': 'AI business assistant',
    'advanced_dashboard': 'Advanced dashboard insights',
    'long_term_history': 'Longer historical data & analytics',
}

PLANS = {
    FREE: {
        'name': 'Free',
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
    return PLANS.get(plan, PLANS[FREE])


def plan_limit(plan, limit_key):
    return get_plan_config(plan)['limits'].get(limit_key)


def plan_has_feature(plan, feature_key):
    return get_plan_config(plan)['features'].get(feature_key, False)


def public_plan_catalog():
    """
    Feature/limit comparison for Free vs Pro (no pricing here - see
    apps.billing.models.get_plan_pricing_catalog() for the three
    billing-cycle prices). Backs the feature checklist on the
    pricing/subscription page.
    """
    catalog = []
    for code in PLANS.keys():
        cfg = get_plan_config(code)
        catalog.append({
            'code': code,
            'name': cfg['name'],
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
