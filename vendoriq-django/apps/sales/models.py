import uuid
from django.db import models
from apps.stores.models import Store, Staff
from apps.products.models import Product
from apps.authentication.models import User


class Sale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sales')
    staff = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True)
    # staff is only set when the person recording the sale has a Staff row -
    # the owner doesn't (ownership is checked separately via Store.owner), so
    # recorded_by points straight at the User for everyone, owner included,
    # to properly attribute "who rang this sale up".
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_recorded')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_profit = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales'
        indexes = [
            # The dashboard, trends, and sales list all filter by store and
            # created_at range - this composite index keeps those queries fast
            # as the sales table grows into the hundreds of thousands of rows.
            models.Index(fields=['store', 'created_at']),
        ]

    def __str__(self):
        return f"Sale {self.id} - {self.store.name}"


class SaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='sale_items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    profit = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'sale_items'
