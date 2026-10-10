import uuid
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('stores', '0002_fix_staff_owner_role'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('phone', models.CharField(blank=True, default='', max_length=30)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('notes', models.CharField(blank=True, default='', max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customers', to='stores.store')),
            ],
            options={'db_table': 'customers', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='CustomerPayment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('method', models.CharField(choices=[('CASH', 'Cash'), ('TRANSFER', 'Bank transfer'), ('CARD', 'Card / POS terminal')], max_length=10)),
                ('client_id', models.UUIDField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='customers.customer')),
                ('recorded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_payments', to='stores.store')),
            ],
            options={'db_table': 'customer_payments', 'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['store', 'name'], name='customers_store_i_b4d7c8_idx'),
        ),
        migrations.AddConstraint(
            model_name='customerpayment',
            constraint=models.UniqueConstraint(condition=Q(('client_id__isnull', False)), fields=('store', 'client_id'), name='customer_payments_store_client_uniq'),
        ),
    ]
