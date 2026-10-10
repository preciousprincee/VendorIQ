import logging
import uuid

from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from apps.billing.entitlements import require_customer_management
from apps.sales import services
from apps.sales.models import Sale
from apps.sales.serializers import SalePaymentSerializer, CustomerPaymentInputSerializer
from apps.sales.services import SaleError
from apps.sales.views import first_error
from apps.stores.base_views import StoreScopedAPIView
from vendoriq.cache_utils import invalidate_store_insights
from .models import Customer, CustomerPayment
from .serializers import CustomerInputSerializer

logger = logging.getLogger(__name__)
FINANCIAL = ['OWNER', 'MANAGER']


def _with_balances(qs):
    return qs.annotate(_t=Sum('sales__total_amount'), _p=Sum('sales__amount_paid'), _r=Sum('sales__amount_refunded'))


def _row(c, balance=None):
    if balance is None:
        balance = (getattr(c, '_t', None) or 0) - (getattr(c, '_p', None) or 0) + (getattr(c, '_r', None) or 0)
    return {
        'id': str(c.id), 'name': c.name, 'phone': c.phone, 'email': c.email, 'notes': c.notes,
        'balance': float(balance), 'created_at': c.created_at,
    }


class CustomerListCreateView(StoreScopedAPIView):
    allowed_roles = None  # a cashier has to be able to find/add the person they're selling to

    def get(self, request, store_id):
        require_customer_management(self.store.owner)
        base = Customer.objects.filter(store=self.store)
        q = (request.query_params.get('q') or '').strip()
        if q:
            # Filter BEFORE annotating: OR-ing two already-annotated querysets
            # double-counts the joined sales rows.
            base = base.filter(Q(name__icontains=q) | Q(phone__icontains=q))
        qs = _with_balances(base)
        rows = [_row(c) for c in qs.order_by('name')[:500]]
        return Response({
            'customers': rows,
            'totalOwed': sum(r['balance'] for r in rows) if self.role in FINANCIAL else None,
        })

    def post(self, request, store_id):
        require_customer_management(self.store.owner)
        serializer = CustomerInputSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        customer = serializer.save(store=self.store)
        return Response({'customer': _row(customer, 0)}, status=status.HTTP_201_CREATED)


class CustomerDetailView(StoreScopedAPIView):
    allowed_roles = None

    def _customer(self):
        return Customer.objects.filter(id=self.kwargs['customer_id'], store=self.store).first()

    def get(self, request, store_id, customer_id):
        require_customer_management(self.store.owner)
        customer = self._customer()
        if customer is None:
            return Response({'error': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'customer': _row(customer, services.customer_balance(customer))})

    def patch(self, request, store_id, customer_id):
        require_customer_management(self.store.owner)
        if self.role not in FINANCIAL:
            return Response({'error': 'Only an owner or manager can edit a customer.'}, status=status.HTTP_403_FORBIDDEN)
        customer = self._customer()
        if customer is None:
            return Response({'error': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CustomerInputSerializer(customer, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({'error': first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({'customer': _row(customer, services.customer_balance(customer))})

    def delete(self, request, store_id, customer_id):
        require_customer_management(self.store.owner)
        if self.role not in FINANCIAL:
            return Response({'error': 'Only an owner or manager can delete a customer.'}, status=status.HTTP_403_FORBIDDEN)
        customer = self._customer()
        if customer is None:
            return Response({'error': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        if customer.sales.exists():
            # Their sales are the debt ledger - deleting the person would lose it.
            return Response({'error': 'This customer has sales on record, so they cannot be deleted.'}, status=status.HTTP_400_BAD_REQUEST)
        customer.delete()
        return Response({'message': 'Customer deleted.'})


class CustomerStatementView(StoreScopedAPIView):
    """GET - what they bought, what they paid, what they still owe."""
    allowed_roles = None

    def get(self, request, store_id, customer_id):
        require_customer_management(self.store.owner)
        customer = Customer.objects.filter(id=customer_id, store=self.store).first()
        if customer is None:
            return Response({'error': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)
        sales = Sale.objects.filter(store=self.store, customer=customer).order_by('-created_at')[:100]
        payments = CustomerPayment.objects.filter(store=self.store, customer=customer).select_related('recorded_by')[:100]
        return Response({
            'customer': _row(customer, services.customer_balance(customer)),
            'sales': [{
                'id': str(s.id), 'receipt_no': s.receipt_no, 'created_at': s.created_at,
                'total_amount': float(s.total_amount), 'amount_paid': float(s.amount_paid - s.amount_refunded),
                'balance_due': float(s.balance_due), 'payment_status': s.payment_status,
            } for s in sales],
            'payments': [{
                'id': str(p.id), 'amount': float(p.amount), 'method': p.method, 'created_at': p.created_at,
                'recorded_by_name': p.recorded_by.name if p.recorded_by else None,
            } for p in payments],
        })


class CustomerPaymentView(StoreScopedAPIView):
    """POST {amount, method, clientId?} - the customer pays off some of what they owe."""
    allowed_roles = None

    def post(self, request, store_id, customer_id):
        body = request.data if isinstance(request.data, dict) else {}
        serializer = CustomerPaymentInputSerializer(data={
            'customerId': str(customer_id), 'amount': body.get('amount'), 'method': body.get('method'),
        })
        if not serializer.is_valid():
            return Response({'error': first_error(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)
        d = serializer.validated_data
        client_id = body.get('clientId') or None
        if client_id is not None:
            try:
                client_id = uuid.UUID(str(client_id))
            except ValueError:
                return Response({'error': 'Invalid clientId.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payment, created = services.collect_customer_payment(
                store=self.store, user=request.user, customer_id=customer_id, amount=d['amount'],
                method=d['method'], client_id=client_id,
            )
        except SaleError as exc:
            return Response({'error': exc.message}, status=exc.status)
        except APIException:
            raise
        invalidate_store_insights(store_id)
        customer = Customer.objects.get(pk=customer_id)
        return Response(
            {'payment': {'id': str(payment.id), 'amount': float(payment.amount), 'method': payment.method},
             'customer': _row(customer, services.customer_balance(customer)), 'duplicate': not created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
