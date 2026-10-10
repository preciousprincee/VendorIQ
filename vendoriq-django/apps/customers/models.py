import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.authentication.models import User
from apps.stores.models import Store

PAYMENT_METHODS = [('CASH', 'Cash'), ('TRANSFER', 'Bank transfer'), ('CARD', 'Card / POS terminal')]


class Customer(models.Model):
    """
    A person a store sells to - mostly so they can buy on credit and pay
    later. What they owe is NOT stored here: it is always computed from their
    sales (sum of total - paid + refunded), so it can never drift out of step
    with the sales ledger.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='customers')
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    notes = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customers'
        ordering = ['name']
        indexes = [models.Index(fields=['store', 'name'])]

    def __str__(self):
        return self.name


class CustomerPayment(models.Model):
    """
    Money received from a customer against what they owe. It is spread over
    their oldest unpaid sales (oldest first) - each slice is a SalePayment row
    pointing back here (see apps/sales/services.collect_customer_payment).
    `client_id` makes it safe to retry (offline sync): the same id is never
    applied twice.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='customer_payments')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    client_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'customer_payments'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['store', 'client_id'], condition=Q(client_id__isnull=False),
                name='customer_payments_store_client_uniq',
            ),
        ]
