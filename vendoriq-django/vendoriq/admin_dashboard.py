"""
Feeds the custom admin dashboard (templates/admin/index.html) via Unfold's
DASHBOARD_CALLBACK hook. This replaces Django admin's default index page -
just a bare list of registered models - with actual at-a-glance numbers
about the whole app: how many users, stores, products, sales, revenue, etc.

Deliberately global (every store, every user), unlike the in-app dashboard
(/insights/dashboard/) which is scoped to one store at a time - this is the
"how's the whole platform doing" view, for whoever has Django admin access.

Scope note: this surfaces metrics backed by real data - users, stores,
products, sales, expenses, invoices, AI chat usage, login events, and (as
of the Free/Pro billing system) subscription/MRR/ARR numbers computed from
the Subscription model. It still does not show support tickets or system
uptime/queue health - those would require building the underlying systems
first, not just a UI for numbers that don't exist yet (see the "Planned"
sections in templates/admin/index.html for those).
"""
from datetime import timedelta

from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.authentication.models import User, LoginEvent
from apps.stores.models import Store, Staff
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem
from apps.expenses.models import Expense
from apps.invoices.models import Invoice
from apps.ai.models import ChatMessage
from apps.billing.models import Subscription, SubscriptionStatus, get_plan_pricing_catalog
from apps.billing.plans import PRO, FREE, BILLING_CYCLE_MONTHS, MONTHLY


def _daily_series(queryset, date_field, days, value_expr=None):
    """
    Builds a zero-filled daily series for the last `days` days - a plain
    list of (date, value) so the template can draw a simple inline SVG
    line, no charting library required. `value_expr` is an aggregate
    expression (e.g. Sum('total_amount')); omitted means "count of rows".
    """
    now = timezone.now()
    # localtime() first - TIME_ZONE is Africa/Lagos (UTC+1), so deriving
    # "start of day" from the raw UTC value would give UTC midnight, not
    # Lagos midnight (see the same fix + longer explanation in
    # apps/insights/views.py). TruncDate(date_field) below already buckets
    # rows by LOCAL calendar day (Django's default when USE_TZ=True), so
    # `start`/`today` must be derived from local time too, or they won't
    # line up with TruncDate's own bucketing and the first/last day of
    # every chart would be wrong.
    local_now = timezone.localtime(now)
    start = (local_now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    annotate_kwargs = {'value': value_expr} if value_expr is not None else {'value': Count('id')}
    rows = (
        queryset.filter(**{f'{date_field}__gte': start})
        .annotate(day=TruncDate(date_field))
        .values('day')
        .annotate(**annotate_kwargs)
    )
    by_day = {row['day']: row['value'] for row in rows}

    series = []
    cursor = start.date()
    today = local_now.date()
    while cursor <= today:
        series.append({'date': cursor.isoformat(), 'value': float(by_day.get(cursor, 0) or 0)})
        cursor += timedelta(days=1)
    return series


def _svg_points(series, width=280, height=56):
    """
    Converts a value series into an SVG <polyline points="..."> string,
    normalized to fit the given viewBox - computed here in Python rather
    than in the template, since Django's template language has no min/max/
    arithmetic to do this cleanly. No charting library needed for a simple
    trend line.
    """
    values = [point['value'] for point in series]
    if not values or len(values) < 2:
        return ''
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step_x = width / (len(values) - 1)
    coords = []
    for i, v in enumerate(values):
        x = i * step_x
        y = height - ((v - lo) / span) * height
        coords.append(f'{x:.1f},{y:.1f}')
    return ' '.join(coords)


def compute_subscription_metrics(recent_limit=6):
    """
    Shared by the main dashboard's "Platform revenue & subscriptions"
    section and the dedicated Revenue page (vendoriq/admin_pages.py) - one
    place computing MRR/ARR/plan breakdown so the two pages can never
    silently disagree with each other.

    See the inline notes below for why this is Python-side iteration
    rather than a queryset .filter(plan='PRO') - short version:
    effective_plan/is_pro_active factor in expiry, complimentary grants,
    and cancellation-in-grace-period, which no single DB column captures.
    """
    # Subscription rows are created lazily (first time anything checks a
    # user's plan - see apps.billing.entitlements.get_subscription), not via
    # a signal on user creation, so an account that has never touched
    # anything billing-related won't have a row yet. That's fine for
    # entitlement checks (Free is the correct default either way) but means
    # the counts below are "of accounts billing has looked at so far", not
    # literally every registered user - noted in the templates rather than
    # silently overcounting Free.
    all_subs = list(Subscription.objects.select_related('user'))
    # Trials are deliberately excluded from "paying" - is_pro_active is True
    # for an active trial (it grants real Pro access) but nobody has paid
    # for it, so it must never count toward MRR/paying counts or it would
    # overstate real revenue the moment trials exist.
    # provider='mock' is the dev-only demo upgrade: it sets a real price_ngn
    # but no money changed hands, so counting it inflated MRR/ARR and the
    # paying-customer count.
    paying_pro_subs = [
        s for s in all_subs
        if s.is_pro_active and not s.is_complimentary and s.status != SubscriptionStatus.TRIAL and s.provider != 'mock'
    ]
    comp_pro_subs = [s for s in all_subs if s.is_pro_active and s.is_complimentary]
    trialing_subs = [s for s in all_subs if s.is_pro_active and s.status == SubscriptionStatus.TRIAL]
    cancelling_subs = [s for s in all_subs if s.is_pro_active and s.cancel_at_period_end]
    lapsed_subs = [s for s in all_subs if not s.is_pro_active and s.plan == PRO]
    free_subs = [s for s in all_subs if not s.is_pro_active and s.plan == FREE]

    pricing_catalog = get_plan_pricing_catalog()
    # 'pro_price' kept as the headline "starting from" figure shown in
    # older templates (index.html/revenue.html) - the Monthly cycle price,
    # since that's the lowest entry price a new signup sees. The full
    # three-cycle breakdown is in 'pricing_catalog' for pages that show it.
    pro_price = next((p['priceNgn'] for p in pricing_catalog if p['billingCycle'] == MONTHLY), 0)
    # MRR normalizes EVERY paying subscriber's locked-in purchase price
    # (price_ngn - the full amount they paid for their WHOLE billing
    # cycle, e.g. \u20a624,000 for an annual plan) down to a monthly-equivalent
    # before summing - summing price_ngn directly would wildly overstate
    # MRR for anyone on the 6-month/annual cycle, since price_ngn is not a
    # monthly figure for those. Never count * today's price (see the
    # per-subscriber comment above) AND never sum raw locked-in prices
    # across different billing cycles - both would misreport revenue.
    mrr = sum(s.price_ngn // BILLING_CYCLE_MONTHS.get(s.billing_cycle, 1) for s in paying_pro_subs)
    tracked_accounts = len(all_subs)
    return {
        'tracked_accounts': tracked_accounts,
        'paying_pro_count': len(paying_pro_subs),
        'comp_pro_count': len(comp_pro_subs),
        'trialing_count': len(trialing_subs),
        'free_count': len(free_subs),
        'cancelling_count': len(cancelling_subs),
        'lapsed_count': len(lapsed_subs),
        'mrr': mrr,
        'arr': mrr * 12,
        'pro_price': pro_price,
        'pricing_catalog': pricing_catalog,
        'conversion_rate': round(len(paying_pro_subs) / tracked_accounts * 100, 1) if tracked_accounts else 0,
        'recent_pro': sorted(
            [s for s in (paying_pro_subs + comp_pro_subs)],
            key=lambda s: s.current_period_start or s.updated_at, reverse=True,
        )[:recent_limit],
        'paying_pro_subs': paying_pro_subs,
        'comp_pro_subs': comp_pro_subs,
        'trialing_subs': trialing_subs,
        'cancelling_subs': cancelling_subs,
        'lapsed_subs': lapsed_subs,
    }


def dashboard_callback(request, context):
    now = timezone.now()
    # See apps/insights/views.py for the full explanation - TIME_ZONE is
    # Africa/Lagos (UTC+1), so day/month boundaries must be derived from
    # localtime() or they land on UTC midnight instead of Lagos midnight.
    local_now = timezone.localtime(now)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # --- Platform Overview KPIs, grouped ------------------------------------
    sales_agg = Sale.objects.aggregate(revenue=Sum('total_amount'), profit=Sum('total_profit'), count=Count('id'))
    today_sales_agg = Sale.objects.filter(created_at__gte=today_start).aggregate(
        revenue=Sum('total_amount'), count=Count('id'))
    expenses_total = Expense.objects.aggregate(total=Sum('amount'))['total'] or 0

    active_store_ids_30d = set(
        Sale.objects.filter(created_at__gte=month_ago).values_list('store_id', flat=True).distinct()
    )

    kpi_groups = [
        {
            'title': 'Users & Stores',
            'cards': [
                {'label': 'Total users', 'value': User.objects.count()},
                {'label': 'New users (7 days)', 'value': User.objects.filter(created_at__gte=week_ago).count()},
                {'label': 'Total stores', 'value': Store.objects.count()},
                {'label': 'Active stores (30 days)', 'value': len(active_store_ids_30d), 'hint': 'had at least one sale'},
                {'label': 'Staff accounts', 'value': Staff.objects.count()},
            ],
        },
        {
            'title': 'Sales',
            'cards': [
                {'label': 'Sales today', 'value': today_sales_agg['count'] or 0},
                {'label': 'Revenue today', 'value': f"₦{(today_sales_agg['revenue'] or 0):,.0f}"},
                {'label': 'Total sales (all time)', 'value': sales_agg['count'] or 0},
                {'label': 'Total revenue (all time)', 'value': f"₦{(sales_agg['revenue'] or 0):,.0f}"},
                {'label': 'Total gross profit (all time)', 'value': f"₦{(sales_agg['profit'] or 0):,.0f}"},
            ],
        },
        {
            'title': 'Inventory',
            'cards': [
                {'label': 'Total products', 'value': Product.objects.count()},
                {'label': 'Low stock', 'value': Product.objects.filter(quantity__lte=F('low_stock_threshold')).count(), 'warn': True},
                {'label': 'Out of stock', 'value': Product.objects.filter(quantity=0).count(), 'warn': True},
            ],
        },
        {
            'title': 'Money out & Invoices',
            'cards': [
                {'label': 'Total expenses (all time)', 'value': f"₦{expenses_total:,.0f}"},
                {'label': 'Total invoices', 'value': Invoice.objects.count()},
                {'label': 'Unpaid/outstanding invoices', 'value': Invoice.objects.exclude(status='PAID').count(), 'warn': True},
            ],
        },
    ]

    # --- Growth trends (last 30 days) --------------------------------------
    new_users_series = _daily_series(User.objects.all(), 'created_at', 30)
    new_stores_series = _daily_series(Store.objects.all(), 'created_at', 30)
    revenue_series = _daily_series(Sale.objects.all(), 'created_at', 30, value_expr=Sum('total_amount'))
    growth = {
        'new_users': {'series': new_users_series, 'points': _svg_points(new_users_series), 'total': int(sum(p['value'] for p in new_users_series))},
        'new_stores': {'series': new_stores_series, 'points': _svg_points(new_stores_series), 'total': int(sum(p['value'] for p in new_stores_series))},
        'revenue': {'series': revenue_series, 'points': _svg_points(revenue_series), 'total': sum(p['value'] for p in revenue_series)},
    }

    # --- Store health --------------------------------------------------------
    all_store_ids = set(Store.objects.values_list('id', flat=True))
    ever_sold_ids = set(Sale.objects.values_list('store_id', flat=True).distinct())
    healthy_ids = active_store_ids_30d
    at_risk_ids = ever_sold_ids - active_store_ids_30d  # sold before, gone quiet
    never_sold_ids = all_store_ids - ever_sold_ids       # onboarded but never made a sale

    store_health = {
        'healthy_count': len(healthy_ids),
        'at_risk_count': len(at_risk_ids),
        'never_sold_count': len(never_sold_ids),
        'at_risk_stores': list(Store.objects.filter(id__in=list(at_risk_ids)[:8]).values('id', 'name')),
    }

    # --- Top lists ------------------------------------------------------------
    top_stores_by_revenue = list(
        Sale.objects.filter(created_at__gte=month_start)
        .values('store__id', 'store__name')
        .annotate(revenue=Sum('total_amount'))
        .order_by('-revenue')[:5]
    )
    top_products = list(
        SaleItem.objects.filter(sale__created_at__gte=month_ago)
        .values('product__name')
        .annotate(units=Sum(F('quantity') - F('returned_quantity')))
        .order_by('-units')[:5]
    )
    most_active_staff = list(
        Sale.objects.filter(created_at__gte=month_ago, recorded_by__isnull=False)
        .values('recorded_by__name', 'recorded_by__email')
        .annotate(sales_count=Count('id'))
        .order_by('-sales_count')[:5]
    )

    # --- AI usage ---------------------------------------------------------------
    ai_messages_today = ChatMessage.objects.filter(role='user', created_at__gte=today_start).count()
    ai_messages_week = ChatMessage.objects.filter(role='user', created_at__gte=week_ago).count()
    ai_active_stores_week = ChatMessage.objects.filter(created_at__gte=week_ago).values('store_id').distinct().count()
    ai_usage = {
        'messages_today': ai_messages_today,
        'messages_week': ai_messages_week,
        'avg_per_active_store': round(ai_messages_week / ai_active_stores_week, 1) if ai_active_stores_week else 0,
    }

    # --- Login/device history (most recent, platform-wide) -------------------
    recent_logins = LoginEvent.objects.select_related('user').order_by('-created_at')[:8]

    # --- Subscriptions & revenue -----------------------------------------------
    subscriptions = compute_subscription_metrics()

    context.update({
        'kpi_groups': kpi_groups,
        'growth': growth,
        'store_health': store_health,
        'top_stores_by_revenue': top_stores_by_revenue,
        'top_products': top_products,
        'most_active_staff': most_active_staff,
        'ai_usage': ai_usage,
        'subscriptions': subscriptions,
        'recent_users': User.objects.order_by('-created_at')[:6],
        'recent_stores': Store.objects.select_related('owner').order_by('-created_at')[:6],
        'recent_sales': Sale.objects.select_related('store', 'recorded_by').order_by('-created_at')[:6],
        'recent_logins': recent_logins,
    })
    return context
