import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.stores.models import Store, Staff
from apps.products.models import Product
from apps.authentication.models import User
from apps.customers.models import PAYMENT_METHODS


class Sale(models.Model):
    """
    MONEY MODEL (read this before touching any amount):

      subtotal         what the items came to at their selling prices
      discount_amount  what was knocked off the whole sale
      total_amount     the NET revenue of the sale = subtotal - discount - returns
      total_profit     the NET profit  = total_amount - cost of the goods not returned
      returned_amount  value of goods taken back (so original total = total_amount + returned_amount)

    total_amount / total_profit stay the "net" figures on purpose: every
    dashboard, trend, expense and export query already sums them, so a
    discount or a return flows into ALL of those reports automatically
    instead of needing a change in each one.

      amount_paid      everything the customer has paid (cash/transfer/card, incl. later debt payments)
      amount_refunded  everything we have handed back
      credit_amount    what was left unpaid when the sale was made (a debt)

    What the customer still owes = total_amount - (amount_paid - amount_refunded).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sales')
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True)
    # staff is only set when the person recording the sale has a Staff row -
    # the owner doesn't (ownership is checked separately via Store.owner), so
    # recorded_by points straight at the User for everyone, owner included,
    # to properly attribute "who rang this sale up".
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_recorded')
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, null=True, blank=True, related_name='sales')

    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_profit = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    returned_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    amount_refunded = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    credit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    cash_tendered = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    change_given = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    note = models.CharField(max_length=200, blank=True, default='')

    # Offline/sync. The phone generates `client_id` when the sale is rung up;
    # the server refuses to create a second sale with the same one, which is
    # what makes "retry until it goes through" safe (a lost response can
    # never double-record a sale).
    client_id = models.UUIDField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)  # set when the sale arrived via offline sync
    # Things the server could only notice AFTER the goods had already left
    # the shop (stock ran out, price changed, discount over the cashier's
    # limit...). The sale is still recorded - it happened - and flagged here
    # for the owner to look at.
    needs_review = models.BooleanField(default=False)
    review_notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales'
        indexes = [
            # The dashboard, trends, and sales list all filter by store and
            # created_at range - this composite index keeps those queries fast
            # as the sales table grows into the hundreds of thousands of rows.
            models.Index(fields=['store', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['store', 'client_id'], condition=Q(client_id__isnull=False),
                name='sales_store_client_id_uniq',
            ),
        ]

    def __str__(self):
        return f"Sale {self.id} - {self.store.name}"

    @property
    def balance_due(self):
        owed = self.total_amount - (self.amount_paid - self.amount_refunded)
        return owed if owed > 0 else Decimal('0')

    @property
    def payment_status(self):
        if self.balance_due <= 0:
            return 'PAID'
        return 'PARTIAL' if (self.amount_paid - self.amount_refunded) > 0 else 'UNPAID'

    @property
    def receipt_no(self):
        # Same value before and after the sale reaches the server (the
        # offline receipt is printed from the client id), so a reprint always matches.
        return str(self.client_id or self.id).replace('-', '')[:8].upper()


class SaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='sale_items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    # Gross line profit (before any sale-level discount) - the discount is
    # applied once, at the Sale level.
    profit = models.DecimalField(max_digits=12, decimal_places=2)
    returned_quantity = models.IntegerField(default=0)

    class Meta:
        db_table = 'sale_items'


class SalePayment(models.Model):
    """One payment received against a sale: at the till, or later against a debt."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    # Set when this slice came from a "customer paid their debt" payment.
    customer_payment = models.ForeignKey('customers.CustomerPayment', on_delete=models.SET_NULL, null=True, blank=True, related_name='allocations')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sale_payments'
        indexes = [models.Index(fields=['created_at'])]


class SaleReturn(models.Model):
    """Goods taken back from a sale (full or partial)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='returns')
    return_value = models.DecimalField(max_digits=12, decimal_places=2)  # value of the goods returned
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))  # money actually handed back
    refund_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, blank=True, default='')
    restocked = models.BooleanField(default=True)
    reason = models.CharField(max_length=200, blank=True, default='')
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'sale_returns'
        ordering = ['-created_at']


class SaleReturnItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, related_name='+')
    quantity = models.IntegerField()

    class Meta:
        db_table = 'sale_return_items'


class Shift(models.Model):
    """
    A cashier's till session: they count the float in, sell, then count the
    cash out and see whether it matches what the system expects.
    Sales do not REQUIRE an open shift (a shop must never be blocked from
    selling), but cash taken while one is open is reconciled against it.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='shifts')
    opened_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shifts_opened')
    opened_at = models.DateTimeField(default=timezone.now)
    opening_float = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    # Snapshot taken at close, so a later correction can't silently rewrite
    # what the person was told when they counted.
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        db_table = 'shifts'
        ordering = ['-opened_at']
        constraints = [
            # One open shift per person per store.
            models.UniqueConstraint(fields=['store', 'opened_by'], condition=Q(closed_at__isnull=True), name='shifts_one_open_per_user'),
        ]
