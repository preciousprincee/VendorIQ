from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from .models import Invoice, InvoiceItem
from .serializers import InvoiceSerializer
from .tasks import send_invoice_email_task
from apps.stores.base_views import StoreScopedAPIView
from apps.stores.permissions import require_store_access
from apps.products.models import Product
from apps.sales.models import Sale
from apps.billing.entitlements import require_invoicing
from vendoriq.cache_utils import invalidate_store_insights


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
        if not items:
            return Response({'error': 'At least one item is required.'}, status=status.HTTP_400_BAD_REQUEST)

        total_amount = Decimal('0')
        items_data = []

        for item in items:
            try:
                product = Product.objects.get(id=item.get('productId'), store=store)
            except (Product.DoesNotExist, ValueError, ValidationError, TypeError):
                # ValueError/ValidationError/TypeError: a malformed or
                # missing productId (not a valid UUID) used to reach
                # Product.objects.get() unvalidated and raise one of these
                # uncaught - a raw 500 instead of a clean 404/400. Same
                # root cause class as the ProtectedError-on-delete bug
                # fixed earlier: an unvalidated value from the request
                # reaching the ORM directly.
                return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
            # Quantity had NO validation at all before this - neither a
            # type check nor a positivity check. A missing quantity would
            # crash on int(None), and a NEGATIVE quantity sailed straight
            # through: unit_price * a negative int produces a negative
            # contribution to total_amount, silently corrupting the
            # invoice total sent to a real customer. Same bug, same fix
            # shape as RecordSaleSerializer in apps/sales/serializers.py -
            # this view just doesn't use a dedicated input serializer, so
            # the check lives inline here instead, matching how unit_price
            # right below is already validated in this same loop.
            try:
                quantity = int(item.get('quantity'))
            except (TypeError, ValueError):
                return Response({'error': 'Quantity must be a whole number.'}, status=status.HTTP_400_BAD_REQUEST)
            if quantity < 1:
                return Response({'error': 'Quantity must be at least 1.'}, status=status.HTTP_400_BAD_REQUEST)
            # Decimal throughout - Invoice.total_amount and
            # InvoiceItem.unit_price are both DecimalFields (exact), so
            # doing this math in float (as this used to) would silently
            # bake binary floating-point rounding into the saved total on
            # every invoice - see the identical fix + fuller explanation
            # in apps/sales/views.py. Going through str() before Decimal()
            # matters here specifically because unitPrice can come from
            # the request body as a JSON number, which Python's json
            # decoder already turns into an imprecise float BEFORE this
            # code ever sees it - Decimal(str(x)) reads the decimal text
            # representation directly rather than inheriting whatever
            # binary float imprecision request.data handed us.
            raw_price = item.get('unitPrice')
            try:
                unit_price = Decimal(str(raw_price)) if raw_price is not None else product.selling_price
            except InvalidOperation:
                return Response({'error': 'Invalid unit price.'}, status=status.HTTP_400_BAD_REQUEST)
            total_amount += unit_price * quantity
            items_data.append({'product': product, 'quantity': quantity, 'unit_price': unit_price})

        invoice = Invoice.objects.create(
            store=store,
            customer_name=request.data.get('customerName'),
            customer_email=request.data.get('customerEmail'),
            customer_phone=request.data.get('customerPhone'),
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

    def post(self, request, store_id, invoice_id):
        store = self.store
        require_invoicing(store.owner)
        try:
            invoice = Invoice.objects.get(id=invoice_id, store=store)
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Allow sending to an address typed in on this request, without
        # requiring the customer's email to have been saved on the invoice.
        recipient = request.data.get('email') or invoice.customer_email
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
        customer_name = (request.data.get('customerName') or '').strip()
        if not customer_name:
            return Response({'error': 'Customer name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sale = Sale.objects.prefetch_related('sale_items__product').get(id=sale_id, store=store)
        except Sale.DoesNotExist:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)

        invoice = Invoice.objects.create(
            store=store,
            customer_name=customer_name,
            customer_email=request.data.get('customerEmail') or None,
            customer_phone=request.data.get('customerPhone') or None,
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
