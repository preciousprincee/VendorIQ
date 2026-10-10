import uuid
from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


def backfill_existing_sales(apps, schema_editor):
    """
    Sales that predate payment tracking: no discount existed, so the subtotal
    is the total, and they were rung up as fully paid - so balances are zero
    and nobody suddenly "owes" anything. (No SalePayment rows are invented:
    the method genuinely wasn't recorded, and the cash reports only cover
    sales made from now on.)
    """
    Sale = apps.get_model('sales', 'Sale')
    Sale.objects.update(subtotal=F('total_amount'), amount_paid=F('total_amount'))


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0001_initial'),
        ('customers', '0001_initial'),
        ('stores', '0002_fix_staff_owner_role'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='sale', name='customer', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sales', to='customers.customer')),
        migrations.AddField(model_name='sale', name='subtotal', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='discount_amount', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='returned_amount', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='amount_paid', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='amount_refunded', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='credit_amount', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='cash_tendered', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='change_given', field=models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.AddField(model_name='sale', name='note', field=models.CharField(blank=True, default='', max_length=200)),
        migrations.AddField(model_name='sale', name='client_id', field=models.UUIDField(blank=True, null=True)),
        migrations.AddField(model_name='sale', name='synced_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='sale', name='needs_review', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='sale', name='review_notes', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='saleitem', name='returned_quantity', field=models.IntegerField(default=0)),
        migrations.AddConstraint(model_name='sale', constraint=models.UniqueConstraint(condition=Q(('client_id__isnull', False)), fields=('store', 'client_id'), name='sales_store_client_id_uniq')),

        migrations.CreateModel(
            name='SalePayment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('method', models.CharField(choices=[('CASH', 'Cash'), ('TRANSFER', 'Bank transfer'), ('CARD', 'Card / POS terminal')], max_length=10)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('customer_payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='allocations', to='customers.customerpayment')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('sale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='sales.sale')),
            ],
            options={'db_table': 'sale_payments'},
        ),
        migrations.AddIndex(model_name='salepayment', index=models.Index(fields=['created_at'], name='sale_paymen_created_e097c8_idx')),
        migrations.CreateModel(
            name='SaleReturn',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('return_value', models.DecimalField(decimal_places=2, max_digits=12)),
                ('refund_amount', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('refund_method', models.CharField(blank=True, choices=[('CASH', 'Cash'), ('TRANSFER', 'Bank transfer'), ('CARD', 'Card / POS terminal')], default='', max_length=10)),
                ('restocked', models.BooleanField(default=True)),
                ('reason', models.CharField(blank=True, default='', max_length=200)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('sale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='returns', to='sales.sale')),
            ],
            options={'db_table': 'sale_returns', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='SaleReturnItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('quantity', models.IntegerField()),
                ('sale_item', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='sales.saleitem')),
                ('sale_return', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='sales.salereturn')),
            ],
            options={'db_table': 'sale_return_items'},
        ),
        migrations.CreateModel(
            name='Shift',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('opened_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('opening_float', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('expected_cash', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('counted_cash', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('variance', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('notes', models.CharField(blank=True, default='', max_length=300)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('opened_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shifts_opened', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shifts', to='stores.store')),
            ],
            options={'db_table': 'shifts', 'ordering': ['-opened_at']},
        ),
        migrations.AddConstraint(model_name='shift', constraint=models.UniqueConstraint(condition=Q(('closed_at__isnull', True)), fields=('store', 'opened_by'), name='shifts_one_open_per_user')),
        migrations.RunPython(backfill_existing_sales, migrations.RunPython.noop),
    ]
