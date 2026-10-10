import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_billing_pricing_overhaul'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CheckoutSession',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reference', models.CharField(max_length=100, unique=True)),
                ('billing_cycle', models.CharField(choices=[('MONTHLY', '1 Month'), ('SIX_MONTH', '6 Months'), ('ANNUAL', '1 Year')], max_length=10)),
                ('amount_kobo', models.PositiveBigIntegerField()),
                ('currency', models.CharField(default='NGN', max_length=3)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('plan_price', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='checkout_sessions', to='billing.planprice')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='checkout_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'billing_checkout_sessions',
                'ordering': ['-created_at'],
            },
        ),
    ]
