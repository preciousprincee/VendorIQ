import uuid
from django.db import models
from apps.stores.models import Store


class Expense(models.Model):
    """
    Tracks miscellaneous expenses and recurring overhead costs for a store
    (rent, utilities, salaries, transport, packaging, etc.) so that true
    net profit (sales profit minus real running costs) can be calculated,
    not just gross product margin.
    """

    class Category(models.TextChoices):
        RENT = 'RENT', 'Rent'
        UTILITIES = 'UTILITIES', 'Utilities'
        SALARIES = 'SALARIES', 'Salaries'
        TRANSPORT = 'TRANSPORT', 'Transport'
        PACKAGING = 'PACKAGING', 'Packaging'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        MISCELLANEOUS = 'MISCELLANEOUS', 'Miscellaneous'
        OTHER = 'OTHER', 'Other'

    class Frequency(models.TextChoices):
        ONE_OFF = 'ONE_OFF', 'One-off'
        DAILY = 'DAILY', 'Daily'
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'
        YEARLY = 'YEARLY', 'Yearly'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='expenses')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.MISCELLANEOUS)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.ONE_OFF)
    is_overhead = models.BooleanField(
        default=False,
        help_text='Recurring running cost (rent, salaries, utilities) vs a one-off miscellaneous expense.'
    )
    incurred_on = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-incurred_on', '-created_at']
        indexes = [
            models.Index(fields=['store', 'incurred_on']),
        ]

    def __str__(self):
        return f"{self.description} - {self.store.name} ({self.amount})"
