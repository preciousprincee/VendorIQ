from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from rest_framework.settings import api_settings
from .models import Invoice, InvoiceItem
from .serializers import InvoiceSerializer
from .tasks import send_invoice_email_task
from apps.stores.base_views import StoreScopedAPIView
from apps.stores.permissions import require_store_access
from apps.products.models import Product
from apps.sales.models import Sale
from apps.billing.entitlements import require_invoicing
from vendoriq.cache_utils import invalidate_store_insights
from vendoriq.throttles import InvoiceSendThrottle

MAX_INVOICE_ITEMS = 200
MAX_MONEY = Decimal('9999999999.99')  # DecimalField(max_digits=12, decimal_places=2)


def _clean_email(value):
    """Returns (email | None, error | None). None for blank input."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if not isinstance(value, str):
        return None, 'Enter a valid email address.'
    value = value.strip()
    try:
        validate_email(value)  # also rejects CR/LF (header injection)
    except ValidationError:
        return None, 'Enter a valid email address.'
    return value, None


def _parse_money(raw):
    """Decimal from request JSON, or None if not a finite, non-negative, storable amount. Decimal('NaN')/'Infinity' parse fine but crash arithmetic and the DB write (HTTP 500)."""
    if isinstance(raw, bool):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite() or value < 0 or value > MAX_MONEY:
        return None
    return value.quantize(Decimal('0.01'))


class InvoiceListCreateView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view/create invoices

    def get(self, request, store_id):
        inv_status = request.query_params.get('status')
        invoices = Invoice.objects.filter(store=self.store)
        if inv_status:
            invoices = invoices.filter(status=inv_status)
        invoices = invoices.prefetch_related('invoice_items__product').order_by('-created_at')[:20]
        return Response({'invoices': InvoiceSerializer(invoices, many=True).data})

    def post(self, request, store_id):
        store = self.store
        require_invoicing(store.owner)
        items = request.data.get('items', [])
        if not isinstance(items, list) or not items:
            return Response({'error': 'At least one item is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(items) > MAX_INVOICE_ITEMS:
            return Response({'error': f'An invoice can have at most {MAX_INVOICE_ITEMS} items.'}, status=status.HTTP_400_BAD_REQUEST)

        # customer_name is NOT NULL: a missing one used to reach the INSERT
        # as None and raise IntegrityError (HTTP 500).
        customer_name = request.data.get('customerName')
        customer_name = customer_name.strip() if isinstance(customer_name, str) else ''
        if not customer_name:
            return Response({'error': 'Customer name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(customer_name) > 255:
            return Response({'error': 'Customer name is too long.'}, status=status.HTTP_400_BAD_REQUEST)
        customer_email, email_error = _clean_email(request.data.get('customerEmail'))
        if email_error:
            return Response({'error': email_error}, status=status.HTTP_400_BAD_REQUEST)
        customer_phone = request.data.get('customerPhone')
        customer_phone = customer_phone.strip()[:20] if isinstance(customer_phone, str) and customer_phone.strip() else None

        total_amount = Decimal('0')
        items_data = []

        for item in items:
            if not isinstance(item, dict):
                return Response({'error': 'Each item must be an object.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                product = Product.objects.get(id=item.get('productId'), store=store)
            except (Product.DoesNotExist, ValueError, ValidationError, TypeError):
                # A malformed or missing productId (not a valid UUID) must
                # be a clean 404, not an uncaught exception.
                return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
            # bool is an int subclass and float('nan') survives int() checks
            # elsewhere - insist on a real positive integer.
            raw_qty = item.get('quantity')
            if isinstance(raw_qty, bool):
                return Response({'error': 'Quantity must be a whole number.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                quantity = int(raw_qty)
            except (TypeError, ValueError, OverflowError):
                return Response({'error': 'Quantity must be a whole number.'}, status=status.HTTP_400_BAD_REQUEST)
            if quantity < 1 or quantity > 1_000_000:
                return Response({'error': 'Quantity must be between 1 and 1,000,000.'}, status=status.HTTP_400_BAD_REQUEST)
            # Decimal throughout (see apps/sales/views.py). Decimal(str(x))
            # reads the decimal text rather than inheriting float drift.
            raw_price = item.get('unitPrice')
            if raw_price is None:
                unit_price = product.selling_price
            else:
                unit_price = _parse_money(raw_price)
                if unit_price is None:
                    return Response({'error': 'Invalid unit price.'}, status=status.HTTP_400_BAD_REQUEST)
            total_amount += unit_price * quantity
            items_data.append({'product': product, 'quantity': quantity, 'unit_price': unit_price})

        if total_amount > MAX_MONEY:
            return Response({'error': 'Invoice total is too large.'}, status=status.HTTP_400_BAD_REQUEST)

        # One transaction: a failure creating an item used to leave an
        # itemless invoice (with a real total) behind.
        with transaction.atomic():
            invoice = Invoice.objects.create(
                store=store,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                total_amount=total_amount,
            )
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=invoice, **item_data)

        invoice.refresh_from_db()
        return Response({'invoice': InvoiceSerializer(invoice).data}, status=status.HTTP_201_CREATED)


class InvoiceDetailView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view; delete narrows further below

    def get(self, request, store_id, invoice_id):
        try:
            invoice = Invoice.objects.prefetch_related('invoice_items__product').get(id=invoice_id, store=self.store)
            return Response({'invoice': InvoiceSerializer(invoice).data})
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, store_id, invoice_id):
        require_store_access(self.store, request.user, ['OWNER', 'MANAGER'])
        try:
            invoice = Invoice.objects.get(id=invoice_id, store=self.store)
            invoice.delete()
            invalidate_store_insights(store_id)
            return Response({'message': 'Invoice deleted.'})
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)


class InvoiceStatusView(StoreScopedAPIView):
    allowed_roles = None

    def patch(self, request, store_id, invoice_id):
        try:
            invoice = Invoice.objects.get(id=invoice_id, store=self.store)
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)
        new_status = request.data.get('status')
        if new_status not in ['DRAFT', 'SENT', 'PAID']:
            return Response({'error': 'Invalid status.'}, status=status.HTTP_400_BAD_REQUEST)
        invoice.status = new_status
        invoice.save()
        invalidate_store_insights(store_id)
        return Response({'invoice': InvoiceSerializer(invoice).data})


class InvoiceSendView(StoreScopedAPIView):
    """Queues the invoice email to the customer and marks it SENT."""
    allowed_roles = None
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, InvoiceSendThrottle]

    def post(self, request, store_id, invoice_id):
        store = self.store
        require_invoicing(store.owner)
        try:
            invoice = Invoice.objects.get(id=invoice_id, store=store)
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Allow sending to an address typed in on this request, without
        # requiring the customer's email to have been saved on the invoice.
        recipient, email_error = _clean_email(request.data.get('email') or invoice.customer_email)
        if email_error:
            return Response({'error': email_error}, status=status.HTTP_400_BAD_REQUEST)
        if not recipient:
            return Response(
                {'error': 'No customer email on file. Add one to send this invoice.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            send_invoice_email_task.delay(str(invoice.id), recipient, store.name)
        except Exception:
            # In local dev (CELERY_TASK_ALWAYS_EAGER=True, no Redis configured)
            # this runs synchronously, so an actual send failure (bad SMTP
            # settings, etc) surfaces here immediately. In production this
            # only fires on a broker connection problem - the send itself
            # happens later on the worker and failures there are logged, not
            # returned to this request.
            return Response(
                {'error': 'Could not queue the email. Check the email settings and try again.'},
                status=status.HTTP_502_BAD_GATEWAY
            )

        if invoice.status == Invoice.Status.DRAFT:
            invoice.status = Invoice.Status.SENT
            invoice.save()
            invalidate_store_insights(store_id)

        return Response({'invoice': InvoiceSerializer(invoice).data, 'message': f'Invoice queued for sending to {recipient}.'})


class CreateInvoiceFromSaleView(StoreScopedAPIView):
    """
    Turns an already-completed sale into a formal invoice - for the walk-in
    customer who, after paying, asks for a proper invoice document. Does not
    touch the original sale; it just copies the line items across.
    """
    allowed_roles = None

    def post(self, request, store_id, sale_id):
        store = self.store
        require_invoicing(store.owner)
        raw_name = request.data.get('customerName')
        customer_name = raw_name.strip() if isinstance(raw_name, str) else ''
        if not customer_name:
            return Response({'error': 'Customer name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(customer_name) > 255:
            return Response({'error': 'Customer name is too long.'}, status=status.HTTP_400_BAD_REQUEST)
        customer_email, email_error = _clean_email(request.data.get('customerEmail'))
        if email_error:
            return Response({'error': email_error}, status=status.HTTP_400_BAD_REQUEST)
        customer_phone = request.data.get('customerPhone')
        customer_phone = customer_phone.strip()[:20] if isinstance(customer_phone, str) and customer_phone.strip() else None

        try:
            sale = Sale.objects.prefetch_related('sale_items__product').get(id=sale_id, store=store)
        except Sale.DoesNotExist:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            invoice = Invoice.objects.create(
                store=store,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                total_amount=sale.total_amount,
            )
            for item in sale.sale_items.all():
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=item.product,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )

        invoice.refresh_from_db()
        return Response({'invoice': InvoiceSerializer(invoice).data}, status=status.HTTP_201_CREATED)
