import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from apps.billing.entitlements import has_feature
from apps.customers.models import Customer
from apps.expenses.models import Expense
from apps.products.models import Product
from apps.stores.base_views import StoreScopedAPIView
from vendoriq.cache_utils import invalidate_store_insights
from . import services
from .models import Sale, Shift
from .serializers import (
    SaleSerializer, RecordSaleSerializer, ReturnInputSerializer, CustomerPaymentInputSerializer,
    SyncSerializer, ShiftSerializer,
)
from .services import SaleError

logger = logging.getLogger(__name__)

FINANCIAL = ['OWNER', 'MANAGER']


def first_error(errors):
    """A DRF error dict -> one readable sentence for the UI."""
    if isinstance(errors, dict):
        for key, value in errors.items():
            msg = first_error(value)
            return msg if key in ('non_field_errors', 'detail') else f'{key}: {msg}'
    if isinstance(errors, (list, tuple)):
        for value in errors:
            if value:
                return first_error(value)
    return str(errors) if errors else 'Invalid data.'


def body_of(request):
    """request.data as a dict - a JSON list/string body would otherwise crash .get() with a 500."""
    return request.data if isinstance(request.data, dict) else {}


def money_dict(d):
    """Decimal -> float, recursively - only ever done at the very edge, for JSON."""
    if isinstance(d, dict):
        return {k: money_dict(v) for k, v in d.items()}
    if hasattr(d, 'quantize'):
        return float(d)
    return d


def sales_queryset():
    return (Sale.objects.select_related('recorded_by', 'customer')
            .prefetch_related('sale_items__product', 'payments', 'returns'))


class SaleListCreateView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view/record sales

    def get(self, request, store_id):
        store = self.store
        qs = sales_queryset().filter(store=store)
        if request.query_params.get('needs_review') == '1':
            qs = qs.filter(needs_review=True)
        customer = request.query_params.get('customer')
        if customer:
            try:
                qs = qs.filter(customer_id=customer)
            except Exception:
                return Response({'error': 'Invalid customer.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = max(1, min(int(request.query_params.get('limit', 50)), 200))
        except ValueError:
            return Response({'error': 'limit must be a whole number.'}, status=status.HTTP_400_BAD_REQUEST)

        sales = qs.order_by('-created_at')[:limit]
        response_data = {'sales': SaleSerializer(sales, many=True, context={'role': self.role}).data}

        # Cashiers can record and view sales, but revenue/profit totals are
        # financial data reserved for owners and managers.
        if self.role in FINANCIAL:
            all_sales = Sale.objects.filter(store=store)
            total = all_sales.aggregate(revenue=Sum('total_amount'), profit=Sum('total_profit'))
            response_data['summary'] = {
                'totalRevenue': float(total['revenue'] or 0),
                'totalProfit': float(total['profit'] or 0),
                'totalTransactions': all_sales.count(),
                'needsReviewCount': all_sales.filter(needs_review=True).count(),
            }
        return Response(response_data)

    def post(self, request, store_id):
        serializer = RecordSaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            sale, created = services.create_sale(
                store=self.store, user=request.user, role=self.role, data=serializer.validated_data, lenient=False,
            )
        except SaleError as exc:
            return Response({'error': exc.message}, status=exc.status)
        except APIException:
            raise  # e.g. UpgradeRequired (customers are a Pro feature): let DRF answer with its own 403
        except Exception:
            # Never echo raw exception text (SQL, table names) to a client.
            logger.error('Recording sale failed for store %s', store_id, exc_info=True)
            return Response({'error': 'Could not record the sale. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        invalidate_store_insights(store_id)
        sale = sales_queryset().get(pk=sale.pk)
        return Response(
            {'sale': SaleSerializer(sale, context={'role': self.role}).data, 'duplicate': not created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SaleDetailView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view a sale; delete narrows further below

    def get(self, request, store_id, sale_id):
        sale = sales_queryset().filter(id=sale_id, store=self.store).first()
        if sale is None:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'sale': SaleSerializer(sale, context={'role': self.role}).data})

    def delete(self, request, store_id, sale_id):
        # Deleting a sale record (e.g. it was entered by mistake) restores the
        # stock it deducted, so inventory numbers stay accurate. Owners/managers
        # can delete any sale; cashiers can only delete sales they personally
        # recorded, so one cashier can't erase another's till record.
        sale = sales_queryset().filter(id=sale_id, store=self.store).first()
        if sale is None:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)

        if self.role == 'CASHIER' and sale.recorded_by_id != request.user.id:
            return Response({'error': 'You can only delete sales you recorded yourself.'}, status=status.HTTP_403_FORBIDDEN)

        # A sale that has become part of the till/ledger history can't just
        # vanish: it would silently change a till count someone already signed
        # off, or leave a customer-payment record pointing at nothing.
        if sale.returns.exists():
            return Response({'error': 'This sale has returns recorded against it, so it can no longer be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        if any(p.customer_payment_id for p in sale.payments.all()):
            return Response({'error': 'A customer debt payment was applied to this sale, so it can no longer be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        if sale.recorded_by_id and Shift.objects.filter(
            store=self.store, opened_by_id=sale.recorded_by_id, closed_at__isnull=False,
            opened_at__lte=sale.created_at, closed_at__gte=sale.created_at,
        ).exists():
            return Response({'error': 'This sale belongs to a shift that has already been closed. Record a return instead.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Two simultaneous deletes of one sale would each restore the
            # stock. Lock the sale row and re-check it still exists.
            if not Sale.objects.select_for_update().filter(id=sale.id).exists():
                return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)
            for item in sorted(sale.sale_items.all(), key=lambda i: str(i.product_id)):
                product = Product.objects.select_for_update().get(id=item.product_id)
                product.quantity += item.quantity
                product.save(update_fields=['quantity', 'updated_at'])
            sale.delete()

        invalidate_store_insights(store_id)
        return Response({'message': 'Sale deleted and stock restored.'})


class SaleReturnView(StoreScopedAPIView):
    """POST /sales/<id>/returns/ - take goods back (owner/manager only: refunds are cash leaving the till)."""
    allowed_roles = FINANCIAL

    def post(self, request, store_id, sale_id):
        serializer = ReturnInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        d = serializer.validated_data
        try:
            sale, ret = services.record_return(
                store=self.store, user=request.user, sale_id=sale_id, items=d['items'],
                refund_method=d.get('refundMethod', ''), restock=d['restock'], reason=d.get('reason', ''),
            )
        except SaleError as exc:
            return Response({'error': exc.message}, status=exc.status)
        invalidate_store_insights(store_id)
        sale = sales_queryset().get(pk=sale.pk)
        return Response({
            'sale': SaleSerializer(sale, context={'role': self.role}).data,
            'refundAmount': float(ret.refund_amount), 'refundMethod': ret.refund_method,
        }, status=status.HTTP_201_CREATED)


class SaleReviewView(StoreScopedAPIView):
    """PATCH /sales/<id>/review/ - the owner has looked at a flagged sale."""
    allowed_roles = FINANCIAL

    def patch(self, request, store_id, sale_id):
        updated = Sale.objects.filter(id=sale_id, store=self.store).update(needs_review=False)
        if not updated:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)
        invalidate_store_insights(store_id)  # the bell's "needs review" count changes
        return Response({'ok': True})


# ---------------------------------------------------------------------------
# Offline sync
# ---------------------------------------------------------------------------

class SyncView(StoreScopedAPIView):
    """
    POST /stores/<id>/sync/ {operations: [{type, clientId, createdAt, payload}]}

    Replays what a device did while offline. EVERY operation is idempotent on
    its clientId, so a batch can be re-sent any number of times (a lost
    response, a flaky connection) without anything being recorded twice.
    Each operation succeeds or fails on its own: one bad sale never blocks the
    others behind it.
    """
    allowed_roles = None

    def post(self, request, store_id):
        serializer = SyncSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)

        results, changed = [], False
        for op in serializer.validated_data['operations']:
            result = {'clientId': str(op['clientId']), 'type': op['type']}
            try:
                if op['type'] == 'sale':
                    payload = RecordSaleSerializer(data={**op['payload'], 'clientId': str(op['clientId'])})
                    if not payload.is_valid():
                        raise SaleError(first_error(payload.errors))
                    sale, created = services.create_sale(
                        store=self.store, user=request.user, role=self.role, data=payload.validated_data,
                        lenient=True, client_time=op.get('createdAt'),
                    )
                    sale = sales_queryset().get(pk=sale.pk)
                    result.update(status='synced' if created else 'duplicate',
                                  sale=SaleSerializer(sale, context={'role': self.role}).data)
                else:
                    payload = CustomerPaymentInputSerializer(data=op['payload'])
                    if not payload.is_valid():
                        raise SaleError(first_error(payload.errors))
                    p = payload.validated_data
                    payment, created = services.collect_customer_payment(
                        store=self.store, user=request.user, customer_id=p['customerId'], amount=p['amount'],
                        method=p['method'], client_id=op['clientId'], client_time=op.get('createdAt'), lenient=True,
                    )
                    result.update(status='synced' if created else 'duplicate', paymentId=str(payment.id))
                changed = changed or result['status'] == 'synced'
            except SaleError as exc:
                result.update(status='rejected', error=exc.message)
            except Exception as exc:
                # UpgradeRequired (customers are a Pro feature) and anything
                # unexpected: report against THIS operation only.
                detail = getattr(exc, 'detail', None)
                if isinstance(exc, APIException) and exc.status_code < 500:
                    msg = (detail.get('error') or detail.get('detail')) if isinstance(detail, dict) else str(detail)
                    result.update(status='rejected', error=str(msg or 'Not allowed.'))
                else:
                    logger.error('Sync operation failed (store %s, %s)', store_id, op['clientId'], exc_info=True)
                    result.update(status='rejected', error='Server error - please try again.', retryable=True)
            results.append(result)

        if changed:
            invalidate_store_insights(store_id)
        return Response({'results': results, 'serverTime': timezone.now()})


class CatalogView(StoreScopedAPIView):
    """
    GET /stores/<id>/catalog/ - everything the till needs to keep working with
    no connection: products (no cost prices - cashiers must never get those),
    customers with their balances, the person's open shift, and the server
    clock (so the device can correct for a wrong clock when stamping offline sales).
    """
    allowed_roles = None

    def get(self, request, store_id):
        store = self.store
        products = list(
            Product.objects.filter(store=store).order_by('name')
            .values('id', 'name', 'barcode', 'selling_price', 'quantity', 'low_stock_threshold')
        )
        for p in products:
            p['id'] = str(p['id'])
            p['selling_price'] = float(p['selling_price'])

        customers, customers_enabled = [], has_feature(store.owner, 'customer_management')
        if customers_enabled:
            rows = (Customer.objects.filter(store=store)
                    .annotate(t=Sum('sales__total_amount'), p=Sum('sales__amount_paid'), r=Sum('sales__amount_refunded'))
                    .order_by('name'))
            customers = [{
                'id': str(c.id), 'name': c.name, 'phone': c.phone,
                'balance': float((c.t or 0) - (c.p or 0) + (c.r or 0)),
            } for c in rows]

        shift = Shift.objects.filter(store=store, opened_by=request.user, closed_at__isnull=True).select_related('opened_by').first()
        return Response({
            'serverTime': timezone.now(),
            'store': {'id': str(store.id), 'name': store.name, 'location': store.location or ''},
            'role': self.role,
            'products': products,
            'customers': customers,
            'customersEnabled': customers_enabled,
            'currentShift': ShiftSerializer(shift).data if shift else None,
            'maxCashierDiscountPercent': settings.CASHIER_MAX_DISCOUNT_PERCENT,
        })


# ---------------------------------------------------------------------------
# Shifts and reports
# ---------------------------------------------------------------------------

def _shift_payload(shift):
    expected, summary = services.shift_expected_cash(shift)
    data = ShiftSerializer(shift).data
    data['live_expected_cash'] = float(expected)
    return {'shift': data, 'summary': money_dict(summary)}


class ShiftListView(StoreScopedAPIView):
    allowed_roles = None

    def get(self, request, store_id):
        qs = Shift.objects.filter(store=self.store).select_related('opened_by', 'closed_by')
        if self.role not in FINANCIAL:
            qs = qs.filter(opened_by=request.user)  # a cashier sees only their own till
        return Response({'shifts': ShiftSerializer(qs[:60], many=True).data})


class CurrentShiftView(StoreScopedAPIView):
    allowed_roles = None

    def get(self, request, store_id):
        shift = Shift.objects.filter(store=self.store, opened_by=request.user, closed_at__isnull=True).select_related('opened_by').first()
        if shift is None:
            return Response({'shift': None})
        return Response(_shift_payload(shift))


class OpenShiftView(StoreScopedAPIView):
    allowed_roles = None

    def post(self, request, store_id):
        try:
            float_amount = body_of(request).get('openingFloat', 0)
            if isinstance(float_amount, bool):
                raise ValueError
            shift = services.open_shift(store=self.store, user=request.user, opening_float=float_amount or 0)
        except (ValueError, TypeError, ArithmeticError):
            return Response({'error': 'Enter a valid opening cash amount.'}, status=status.HTTP_400_BAD_REQUEST)
        except SaleError as exc:
            return Response({'error': exc.message}, status=exc.status)
        return Response(_shift_payload(shift), status=status.HTTP_201_CREATED)


class ShiftDetailView(StoreScopedAPIView):
    allowed_roles = None

    def _get(self, request, shift_id):
        shift = Shift.objects.filter(id=shift_id, store=self.store).select_related('opened_by', 'closed_by').first()
        if shift is None or (self.role not in FINANCIAL and shift.opened_by_id != request.user.id):
            return None
        return shift

    def get(self, request, store_id, shift_id):
        shift = self._get(request, shift_id)
        if shift is None:
            return Response({'error': 'Shift not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_shift_payload(shift))


class CloseShiftView(ShiftDetailView):
    def post(self, request, store_id, shift_id):
        shift = self._get(request, shift_id)
        if shift is None:
            return Response({'error': 'Shift not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            counted = body_of(request).get('countedCash')
            if counted is None or isinstance(counted, bool):
                raise ValueError
            shift = services.close_shift(shift=shift, user=request.user, counted_cash=counted, notes=body_of(request).get('notes') or '')
        except (ValueError, TypeError, ArithmeticError):
            return Response({'error': 'Enter the cash you counted.'}, status=status.HTTP_400_BAD_REQUEST)
        except SaleError as exc:
            return Response({'error': exc.message}, status=exc.status)
        shift = Shift.objects.select_related('opened_by', 'closed_by').get(pk=shift.pk)
        return Response(_shift_payload(shift))


class DailyReportView(StoreScopedAPIView):
    """GET /reports/daily/?date=YYYY-MM-DD - the end-of-day summary (owner/manager)."""
    allowed_roles = FINANCIAL

    def get(self, request, store_id):
        raw = request.query_params.get('date')
        try:
            day = datetime.strptime(raw, '%Y-%m-%d').date() if raw else timezone.localdate()
        except ValueError:
            return Response({'error': 'date must be YYYY-MM-DD.'}, status=status.HTTP_400_BAD_REQUEST)
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(day, time.min), tz)
        end = start + timedelta(days=1)
        summary = services.build_summary(self.store, start, end)
        expenses = Expense.objects.filter(store=self.store, incurred_on=day).aggregate(t=Sum('amount'))['t'] or 0
        net = Sale.objects.filter(store=self.store, created_at__gte=start, created_at__lt=end).aggregate(
            revenue=Sum('total_amount'), profit=Sum('total_profit'))
        return Response({
            'date': day.isoformat(),
            'summary': money_dict(summary),
            'netSales': float(net['revenue'] or 0),
            'netProfit': float(net['profit'] or 0),
            'expenses': float(expenses),
        })
