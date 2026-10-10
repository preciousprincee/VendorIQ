from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum
from django.utils import timezone
from django.http import HttpResponse
import csv
import re
from django.utils.dateparse import parse_date
from .models import Expense
from .serializers import ExpenseSerializer
from apps.stores.base_views import StoreScopedAPIView
from apps.sales.models import Sale
from apps.billing.entitlements import require_data_export, require_advanced_profit_analytics
from vendoriq.cache_utils import (
    profitability_key, PROFITABILITY_TTL,
    safe_cache_get, safe_cache_set, invalidate_store_insights,
)

# Managers can record and review misc expenses/overhead day-to-day.
EXPENSE_ROLES = ['OWNER', 'MANAGER']
# True net profit and the full bookkeeping export reveal the complete cost
# structure (rent, salaries, overhead) rolled up against revenue - reserved
# for the owner only, even though managers can enter the underlying expenses.
OWNER_ONLY = ['OWNER']


def _parse_date_param(request, name):
    """Returns (date | None, error_response | None). A malformed ?start= / ?end= used to reach the ORM as a raw string and raise ValidationError -> HTTP 500."""
    raw = request.query_params.get(name)
    if not raw:
        return None, None
    parsed = None
    try:
        parsed = parse_date(raw)
    except ValueError:
        parsed = None
    if parsed is None:
        return None, Response({'error': f'{name} must be a date in YYYY-MM-DD format.'}, status=status.HTTP_400_BAD_REQUEST)
    return parsed, None


class ExpenseListCreateView(StoreScopedAPIView):
    allowed_roles = EXPENSE_ROLES

    def get(self, request, store_id):
        expenses = Expense.objects.filter(store=self.store)

        category = request.query_params.get('category')
        if category:
            expenses = expenses.filter(category=category)

        start, err = _parse_date_param(request, 'start')
        if err:
            return err
        end, err = _parse_date_param(request, 'end')
        if err:
            return err
        if start:
            expenses = expenses.filter(incurred_on__gte=start)
        if end:
            expenses = expenses.filter(incurred_on__lte=end)

        total = expenses.aggregate(total=Sum('amount'))['total'] or 0
        overhead_total = expenses.filter(is_overhead=True).aggregate(total=Sum('amount'))['total'] or 0
        misc_total = expenses.filter(is_overhead=False).aggregate(total=Sum('amount'))['total'] or 0

        return Response({
            'expenses': ExpenseSerializer(expenses, many=True).data,
            'summary': {
                'total': float(total),
                'overheadTotal': float(overhead_total),
                'miscTotal': float(misc_total),
                'count': expenses.count(),
            }
        })

    def post(self, request, store_id):
        serializer = ExpenseSerializer(data=request.data)
        if serializer.is_valid():
            expense = serializer.save(store=self.store)
            invalidate_store_insights(store_id)
            return Response({'expense': ExpenseSerializer(expense).data}, status=status.HTTP_201_CREATED)
        return Response({'error': next(iter(serializer.errors.values()))[0]}, status=status.HTTP_400_BAD_REQUEST)


class ExpenseDetailView(StoreScopedAPIView):
    allowed_roles = EXPENSE_ROLES

    def get_expense(self, expense_id):
        try:
            return Expense.objects.get(id=expense_id, store=self.store)
        except Expense.DoesNotExist:
            return None

    def patch(self, request, store_id, expense_id):
        expense = self.get_expense(expense_id)
        if not expense:
            return Response({'error': 'Expense not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExpenseSerializer(expense, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            invalidate_store_insights(store_id)
            return Response({'expense': serializer.data})
        return Response({'error': next(iter(serializer.errors.values()))[0]}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, store_id, expense_id):
        expense = self.get_expense(expense_id)
        if not expense:
            return Response({'error': 'Expense not found.'}, status=status.HTTP_404_NOT_FOUND)
        expense.delete()
        invalidate_store_insights(store_id)
        return Response({'message': 'Expense deleted.'})


class ProfitabilityView(StoreScopedAPIView):
    """
    True store profitability: sales profit minus misc expenses and overhead
    costs, for today / this month / all-time - answers "is this store
    actually in profit?" rather than just gross product margin.
    """
    allowed_roles = OWNER_ONLY

    def get(self, request, store_id):
        store = self.store
        require_advanced_profit_analytics(store.owner)
        cache_key = profitability_key(store_id)
        cached = safe_cache_get(cache_key)
        if cached is not None:
            return Response(cached)

        now = timezone.now()
        # See apps/insights/views.py for why this must go through
        # localtime() first - TIME_ZONE is Africa/Lagos (UTC+1), so
        # .replace() on the raw UTC value gives UTC midnight, not Lagos
        # midnight, which would misattribute an hour of profit/expense data
        # each day.
        local_now = timezone.localtime(now)
        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        def period(sales_since, expenses_since):
            sales_profit = Sale.objects.filter(store=store, created_at__gte=sales_since).aggregate(
                total=Sum('total_profit'))['total'] or 0
            revenue = Sale.objects.filter(store=store, created_at__gte=sales_since).aggregate(
                total=Sum('total_amount'))['total'] or 0
            expenses_total = Expense.objects.filter(store=store, incurred_on__gte=expenses_since).aggregate(
                total=Sum('amount'))['total'] or 0
            return {
                'revenue': float(revenue),
                'salesProfit': float(sales_profit),
                'expenses': float(expenses_total),
                'netProfit': float(sales_profit) - float(expenses_total),
            }

        all_time_expenses = Expense.objects.filter(store=store).aggregate(total=Sum('amount'))['total'] or 0
        all_time_sales_profit = Sale.objects.filter(store=store).aggregate(total=Sum('total_profit'))['total'] or 0
        all_time_revenue = Sale.objects.filter(store=store).aggregate(total=Sum('total_amount'))['total'] or 0

        payload = {
            'today': period(today_start, today_start.date()),
            'month': period(month_start, month_start.date()),
            'allTime': {
                'revenue': float(all_time_revenue),
                'salesProfit': float(all_time_sales_profit),
                'expenses': float(all_time_expenses),
                'netProfit': float(all_time_sales_profit) - float(all_time_expenses),
            },
        }
        safe_cache_set(cache_key, payload, PROFITABILITY_TTL)
        return Response(payload)


class ExportRecordsView(StoreScopedAPIView):
    """
    Downloads a CSV bookkeeping record - sales, expenses, and a profit & loss
    summary for a date range - the kind of paper trail typically requested
    when applying for a business loan or line of credit.
    """
    allowed_roles = OWNER_ONLY

    def get(self, request, store_id):
        store = self.store
        require_data_export(store.owner)
        start, err = _parse_date_param(request, 'start')
        if err:
            return err
        end, err = _parse_date_param(request, 'end')
        if err:
            return err

        def csv_safe(value):
            """
            Neutralizes CSV/formula injection (CWE-1236): a cell value
            starting with =, +, -, @, or a tab/CR is interpreted as a
            FORMULA by Excel/Sheets when the file is later opened, not as
            plain text. sale.recorded_by.name comes from a user's own
            display name (freely settable at registration by anyone) and
            expense.description is free text any staff member with expense
            access can set - both are attacker-reachable with nothing more
            than an ordinary account. Without this, someone could register
            as e.g. `=cmd|'/c calc.exe'!A1` and have it execute the moment
            the STORE OWNER opens this exact export - for the loan/credit
            application this view's docstring says it exists to produce.
            Prefixing with a single quote is the standard mitigation:
            spreadsheet programs treat a leading quote as "force this cell
            to text", neutralizing the formula without visibly mangling any
            ordinary name/description that doesn't start with one of these
            characters.
            """
            text = str(value)
            if text and text[0] in ('=', '+', '-', '@', '\t', '\r'):
                return "'" + text
            return text

        sales = Sale.objects.filter(store=store).select_related('recorded_by').order_by('created_at')
        expenses = Expense.objects.filter(store=store).order_by('incurred_on')
        if start:
            sales = sales.filter(created_at__date__gte=start)
            expenses = expenses.filter(incurred_on__gte=start)
        if end:
            sales = sales.filter(created_at__date__lte=end)
            expenses = expenses.filter(incurred_on__lte=end)

        total_revenue = sales.aggregate(t=Sum('total_amount'))['t'] or 0
        total_sales_profit = sales.aggregate(t=Sum('total_profit'))['t'] or 0
        total_expenses = expenses.aggregate(t=Sum('amount'))['t'] or 0

        response = HttpResponse(content_type='text/csv')
        # The store name is user-controlled: a quote breaks out of the
        # Content-Disposition value and a newline makes Django raise
        # BadHeaderError (HTTP 500). Reduce it to a safe ASCII slug.
        safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', store.name).strip('_')[:60] or 'store'
        filename = f"{safe_name}_bookkeeping_{start or 'all'}_{end or timezone.localdate()}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        writer = csv.writer(response)

        writer.writerow([f'VendorIQ Bookkeeping Records - {csv_safe(store.name)}'])
        writer.writerow([f'Period: {start or "inception"} to {end or "present"}'])
        writer.writerow([])

        writer.writerow(['PROFIT & LOSS SUMMARY'])
        writer.writerow(['Total Revenue', f'{total_revenue:.2f}'])
        writer.writerow(['Total Cost of Goods Sold', f'{float(total_revenue) - float(total_sales_profit):.2f}'])
        writer.writerow(['Gross Profit', f'{total_sales_profit:.2f}'])
        writer.writerow(['Total Expenses & Overhead', f'{total_expenses:.2f}'])
        writer.writerow(['Net Profit', f'{float(total_sales_profit) - float(total_expenses):.2f}'])
        writer.writerow([])

        writer.writerow(['SALES TRANSACTIONS'])
        writer.writerow(['Date', 'Sale ID', 'Recorded By', 'Revenue', 'Gross Profit'])
        for sale in sales:
            writer.writerow([
                sale.created_at.strftime('%Y-%m-%d %H:%M'),
                str(sale.id),
                csv_safe(sale.recorded_by.name) if sale.recorded_by else 'Unknown',
                f'{sale.total_amount:.2f}',
                f'{sale.total_profit:.2f}',
            ])
        writer.writerow([])

        writer.writerow(['EXPENSES & OVERHEAD'])
        writer.writerow(['Date', 'Category', 'Description', 'Type', 'Amount'])
        for expense in expenses:
            writer.writerow([
                expense.incurred_on.strftime('%Y-%m-%d'),
                expense.get_category_display(),
                csv_safe(expense.description),
                'Overhead' if expense.is_overhead else 'Misc',
                f'{expense.amount:.2f}',
            ])

        return response
