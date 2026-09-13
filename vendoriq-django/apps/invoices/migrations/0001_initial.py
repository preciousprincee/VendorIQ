import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('stores', '0001_initial'),
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('customer_name', models.CharField(max_length=255)),
                ('customer_email', models.EmailField(blank=True, max_length=254, null=True)),
                ('customer_phone', models.CharField(blank=True, max_length=20, null=True)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(choices=[('DRAFT', 'Draft'), ('SENT', 'Sent'), ('PAID', 'Paid')], default='DRAFT', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='stores.store')),
            ],
            options={
                'db_table': 'invoices',
            },
        ),
        migrations.CreateModel(
            name='InvoiceItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('quantity', models.IntegerField()),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoice_items', to='invoices.invoice')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='products.product')),
            ],
            options={
                'db_table': 'invoice_items',
            },
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['store', 'status'], name='invoices_store_i_d4e5f6_idx'),
        ),
        migrations.AddIndex(
            model_name='invoice',
            index=models.Index(fields=['store', 'created_at'], name='invoices_store_i_g7h8i9_idx'),
        ),
    ]
