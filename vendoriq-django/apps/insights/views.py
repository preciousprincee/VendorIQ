from rest_framework.response import Response
from django.db.models import Sum, Count, F, DecimalField
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from apps.stores.base_views import StoreScopedAPIView
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem
from apps.expenses.models import Expense
from apps.invoices.models import Invoice
from apps.billing.entitlements import clamp_trend_days
from vendoriq.cache_utils import (
    dashboard_key, trend_key, notifications_key,
    DASHBOARD_TTL, TREND_TTL, NOTIFICATIONS_TTL,
    safe_cache_get, safe_cache_set,
)

# Revenue/profit/dashboard figures are financial data - cashiers do not get access.
FINANCIAL_ROLES = ['OWNER', 'MANAGER']


class DashboardView(StoreScopedAPIView):
    allowed_roles = FINANCIAL_ROLES

    def get(self, request, store_id):
        store = self.store
        cache_key = dashboard_key(store_id)
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return Response(cached)

        now = timezone.now()
        # timezone.now() is UTC internally (Django always stores/returns UTC
        # when USE_TZ=True) - but TIME_ZONE is Africa/Lagos (UTC+1), so
        # deriving "today"/"this month" boundaries by calling .replace() on
        # the raw UTC value gives UTC midnight, not Lagos midnight. For the
        # ~1 hour after real Lagos midnight each day, that made today_start
        # sit a full 23 hours too early - "Today's Revenue" would silently
        # include all of yesterday's sales too. localtime() converts to the
        # actual Lagos wall-clock time first, so .replace(hour=0) below
        # correctly zeroes out the LOCAL hour instead of the UTC one.
        local_now = timezone.localtime(now)
        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        week_start = now - timedelta(days=7)
        prior_week_start = week_start - timedelta(days=7)
        month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Same-length "month to date" window from the previous calendar month,
        # e.g. if today is the 12th, this is the 1st-12th of last month - not
        # last month's full total, which would always make a partial current
        # month look artificially worse regardless of how the store is
        # actually doing.
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_elapsed_this_month = (now - month_start).days
        prev_month_to_date_end = prev_month_start + timedelta(days=days_elapsed_this_month, hours=local_now.hour, minutes=local_now.minute, seconds=local_now.second)

        def period_summary(sales_start, sales_end, expenses_start_date, expenses_end_date):
            sales_qs = Sale.objects.filter(store=store, created_at__gte=sales_start)
            if sales_end is not None:
                sales_qs = sales_qs.filter(created_at__lt=sales_end)
            sales_agg = sales_qs.aggregate(revenue=Sum('total_amount'), profit=Sum('total_profit'), count=Count('id'))

            expenses_qs = Expense.objects.filter(store=store, incurred_on__gte=expenses_start_date)
            if expenses_end_date is not None:
                expenses_qs = expenses_qs.filter(incurred_on__lt=expenses_end_date)
            expenses_total = float(expenses_qs.aggregate(total=Sum('amount'))['total'] or 0)

            sales_profit = float(sales_agg['profit'] or 0)
            return {
                'revenue': float(sales_agg['revenue'] or 0),
                'salesProfit': sales_profit,
                'expenses': expenses_total,
                'netProfit': sales_profit - expenses_total,
                'transactions': sales_agg['count'],
            }

        today = period_summary(today_start, None, today_start.date(), None)
        yesterday = period_summary(yesterday_start, today_start, yesterday_start.date(), today_start.date())
        week = period_summary(week_start, None, week_start.date(), None)
        prior_week = period_summary(prior_week_start, week_start, prior_week_start.date(), week_start.date())
        month = period_summary(month_start, None, month_start.date(), None)
        prev_month_to_date = period_summary(prev_month_start, prev_month_to_date_end, prev_month_start.date(), prev_month_to_date_end.date())

        products = Product.objects.filter(store=store)
        # Aggregate in the database rather than loading every product row into
        # Python - the dashboard is the most frequently hit endpoint, so this
        # is the single highest-impact query to keep cheap under load.
        inventory_agg = products.aggregate(
            total=Count('id'),
            total_stock_value=Sum(F('cost_price') * F('quantity'), output_field=DecimalField()),
            total_retail_value=Sum(F('selling_price') * F('quantity'), output_field=DecimalField()),
        )
        total_stock_value = float(inventory_agg['total_stock_value'] or 0)
        total_retail_value = float(inventory_agg['total_retail_value'] or 0)

        low_stock = products.filter(quantity__lte=F('low_stock_threshold')).order_by('quantity')[:10]
        low_stock_data = [{'id': str(p.id), 'name': p.name, 'quantity': p.quantity, 'lowStockThreshold': p.low_stock_threshold} for p in low_stock]

        # Best sellers
        best_sellers = SaleItem.objects.filter(
            sale__store=store,
            sale__created_at__gte=month_start
        ).values('product__id', 'product__name').annotate(
            total_sold=Sum('quantity')
        ).order_by('-total_sold')[:5]

        best_sellers_data = [{
            'productId': str(b['product__id']),
            'product': {'name': b['product__name']},
            '_sum': {'quantity': b['total_sold']}
        } for b in best_sellers]

        sold_ids = [b['product__id'] for b in best_sellers]
        dead_stock = products.filter(quantity__gt=0).exclude(id__in=sold_ids)[:5]
        dead_stock_data = [{'id': str(p.id), 'name': p.name, 'quantity': p.quantity} for p in dead_stock]

        payload = {
            'today': today,
            'yesterday': yesterday,
            'week': week,
            'priorWeek': prior_week,
            'month': month,
            'prevMonthToDate': prev_month_to_date,
            'inventory': {
                'totalProducts': inventory_agg['total'],
                'totalStockValue': total_stock_value,
                'totalRetailValue': total_retail_value,
                'potentialProfit': total_retail_value - total_stock_value,
            },
            'lowStockProducts': low_stock_data,
            'bestSellers': best_sellers_data,
            'deadStock': dead_stock_data,
        }
        safe_cache_set(cache_key, payload, DASHBOARD_TTL)
        return Response(payload)


class TrendView(StoreScopedAPIView):
    allowed_roles = FINANCIAL_ROLES

    def get(self, request, store_id):
        store = self.store
        requested_days = int(request.query_params.get('days', 30))
        days = clamp_trend_days(store.owner, requested_days)

        cache_key = trend_key(store_id, days)
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return Response(cached)

        now = timezone.now()
        start_date = now - timedelta(days=days)

        # Group by day in the database instead of pulling every sale row into
        # Python and summing them by hand - identical result, far less data
        # transferred and no per-row model hydration.
        sales_rows = (
            Sale.objects.filter(store=store, created_at__gte=start_date)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(revenue=Sum('total_amount'), profit=Sum('total_profit'), transactions=Count('id'))
        )
        by_day = {row['day']: row for row in sales_rows}

        expense_rows = (
            Expense.objects.filter(store=store, incurred_on__gte=start_date.date())
            .values('incurred_on')
            .annotate(total=Sum('amount'))
        )
        expenses_by_day = {row['incurred_on']: float(row['total'] or 0) for row in expense_rows}

        # Fill every calendar day in the window, not just days that happen to
        # have a sale - otherwise a quiet day drops out of the series
        # entirely instead of showing as a real dip, and the line's x-axis
        # spacing gets thrown off by the gap.
        trend = []
        cursor = start_date.date()
        today = now.date()
        while cursor <= today:
            row = by_day.get(cursor)
            revenue = float(row['revenue'] or 0) if row else 0.0
            sales_profit = float(row['profit'] or 0) if row else 0.0
            transactions = row['transactions'] if row else 0
            expenses = expenses_by_day.get(cursor, 0.0)
            trend.append({
                'date': cursor.strftime('%Y-%m-%d'),
                'revenue': revenue,
                'salesProfit': sales_profit,
                'expenses': expenses,
                'profit': sales_profit - expenses,  # net profit - what the dashboard sparkline/insights chart plot
                'transactions': transactions,
            })
            cursor += timedelta(days=1)

        payload = {
            'trend': trend,
            # Lets the frontend show a "showing the last N days - upgrade
            # for longer history" nudge when the requested range got
            # clamped for a Free-plan store, instead of silently returning
            # fewer days than asked for with no explanation.
            'requestedDays': requested_days,
            'limited': days < requested_days,
        }
        safe_cache_set(cache_key, payload, TREND_TTL)
        return Response(payload)


class NotificationsView(StoreScopedAPIView):
    """
    Computed on the fly from existing data rather than a stored notification
    log - out-of-stock/low-stock products and invoices that have sat unpaid
    for a while are the "important" alerts an owner/manager needs to act on.
    """
    allowed_roles = FINANCIAL_ROLES

    def get(self, request, store_id):
        store = self.store
        cache_key = notifications_key(store_id)
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return Response(cached)

        notifications = []

        out_of_stock = Product.objects.filter(store=store, quantity=0)
        for p in out_of_stock[:10]:
            notifications.append({
                'id': f'out-of-stock-{p.id}',
                'type': 'out_of_stock',
                'severity': 'high',
                'message': f'{p.name} is out of stock',
                'link': '/products',
                'createdAt': p.updated_at,
            })

        low_stock = Product.objects.filter(store=store, quantity__gt=0, quantity__lte=F('low_stock_threshold'))
        for p in low_stock[:10]:
            notifications.append({
                'id': f'low-stock-{p.id}',
                'type': 'low_stock',
                'severity': 'medium',
                'message': f'{p.name} is running low ({p.quantity} left)',
                'link': '/products',
                'createdAt': p.updated_at,
            })

        stale_cutoff = timezone.now() - timedelta(days=14)
        stale_invoices = Invoice.objects.filter(store=store, status='SENT', created_at__lte=stale_cutoff)
        for inv in stale_invoices[:10]:
            days_out = (timezone.now() - inv.created_at).days
            notifications.append({
                'id': f'stale-invoice-{inv.id}',
                'type': 'stale_invoice',
                'severity': 'medium',
                'message': f'Invoice for {inv.customer_name} has been unpaid for {days_out} days',
                'link': '/invoices',
                'createdAt': inv.created_at,
            })

        notifications.sort(key=lambda n: n['createdAt'], reverse=True)
        payload = {'notifications': notifications, 'count': len(notifications)}
        safe_cache_set(cache_key, payload, NOTIFICATIONS_TTL)
        return Response(payload)
