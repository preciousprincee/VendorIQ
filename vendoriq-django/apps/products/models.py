import uuid
from django.db import models
from django.db.models import Q
from apps.authentication.models import User
from apps.stores.models import Store


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=5)
    category = models.CharField(max_length=100, blank=True, null=True)
    supplier = models.CharField(max_length=255, blank=True, null=True)
    photo = models.ImageField(upload_to='products/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        indexes = [
            # Speeds up the checkout barcode scanner's lookup, and product search.
            models.Index(fields=['store', 'barcode']),
        ]

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_stock_threshold

    @property
    def profit_margin(self):
        if self.selling_price > 0:
            return float((self.selling_price - self.cost_price) / self.selling_price * 100)
        return 0


class ProductDeletionRequest(models.Model):
    """
    A cashier cannot delete a product, but can ask for it to be deleted (say it
    was added by mistake). The request carries a remark explaining why and
    goes to the owner and every manager of the store; the product is only
    deleted once one of them approves. The row is kept afterwards as a record
    of who asked, who decided, and why - which is why the product's name is
    copied here (the product itself is gone once approved).
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Waiting for approval'
        APPROVED = 'APPROVED', 'Approved (product deleted)'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='product_deletion_requests')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='deletion_requests')
    product_name = models.CharField(max_length=255)
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    remark = models.CharField(max_length=300)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'product_deletion_requests'
        ordering = ['-created_at']
        constraints = [
            # One open request per product - two cashiers asking for the same
            # thing shouldn't send the managers the same question twice.
            models.UniqueConstraint(fields=['product'], condition=Q(status='PENDING'), name='product_one_pending_deletion_request'),
        ]

    def __str__(self):
        return f'{self.product_name} ({self.status})'
