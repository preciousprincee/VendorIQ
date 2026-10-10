import json
import re

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.settings import api_settings

from apps.billing.entitlements import require_cloud_backup
from apps.customers.models import Customer, CustomerPayment
from apps.expenses.models import Expense
from apps.invoices.models import Invoice, InvoiceItem
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem, Shift
from vendoriq.throttles import BackupThrottle
from .base_views import StoreScopedAPIView

FORMAT_VERSION = 1


class StoreBackupView(StoreScopedAPIView):
    """
    GET /stores/<id>/backup/ - one JSON file with EVERYTHING the store has:
    products, customers, sales (with their items, payments and returns),
    customer payments, expenses, invoices and shifts. Owner only (it contains
    cost prices and profit) and a Pro feature ("Cloud backup").

    This is a point-in-time copy the owner keeps; the live data itself already
    lives in VendorIQ's cloud database for every plan.
    """
    allowed_roles = ['OWNER']
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, BackupThrottle]

    def get(self, request, store_id):
        store = self.store
        require_cloud_backup(store.owner)

        def rows(qs):
            return list(qs.values())

        sale_ids = list(Sale.objects.filter(store=store).values_list('id', flat=True))
        data = {
            'format_version': FORMAT_VERSION,
            'generated_at': timezone.now(),
            'store': {'id': store.id, 'name': store.name, 'location': store.location},
            'products': rows(Product.objects.filter(store=store).order_by('name')),
            'customers': rows(Customer.objects.filter(store=store).order_by('name')),
            'customer_payments': rows(CustomerPayment.objects.filter(store=store)),
            'sales': rows(Sale.objects.filter(store=store).order_by('created_at')),
            'sale_items': rows(SaleItem.objects.filter(sale_id__in=sale_ids)),
            'sale_payments': rows(SalePayment.objects.filter(sale_id__in=sale_ids)),
            'sale_returns': rows(SaleReturn.objects.filter(sale_id__in=sale_ids)),
            'sale_return_items': rows(SaleReturnItem.objects.filter(sale_return__sale_id__in=sale_ids)),
            'expenses': rows(Expense.objects.filter(store=store)),
            'invoices': rows(Invoice.objects.filter(store=store)),
            'invoice_items': rows(InvoiceItem.objects.filter(invoice__store=store)),
            'shifts': rows(Shift.objects.filter(store=store)),
        }
        body = json.dumps(data, cls=DjangoJSONEncoder)
        safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', store.name).strip('_')[:50] or 'store'
        response = HttpResponse(body, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="vendoriq-backup-{safe_name}-{timezone.localdate()}.json"'
        response['Cache-Control'] = 'no-store'
        return response
