import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


BILLING_CYCLE_CHOICES = [
    ('MONTHLY', '1 Month'),
    ('SIX_MONTH', '6 Months'),
    ('ANNUAL', '1 Year'),
]

# Launch pricing, in kobo (1 Naira = 100 kobo) - matches apps/billing/plans.py
# PRICE_SEED_KOBO at the time this migration was written. Hardcoded here
# (not imported from plans.py) deliberately: a migration must keep working
# exactly as written even if the seed constants in code change later.
SEED_PRICES_KOBO = {
    'MONTHLY': 500000,     # \u20a65,000
    'SIX_MONTH': 1500000,  # \u20a615,000
    'ANNUAL': 2400000,     # \u20a624,000
}


def seed_plan_prices(apps, schema_editor):
    PlanPrice = apps.get_model('billing', 'PlanPrice')
    for cycle, price_kobo in SEED_PRICES_KOBO.items():
        if not PlanPrice.objects.filter(billing_cycle=cycle, is_current=True).exists():
            PlanPrice.objects.create(billing_cycle=cycle, price_kobo=price_kobo, currency='NGN', is_current=True, note='Launch pricing (seeded by migration).')


def noop_reverse(apps, schema_editor):
    pass


def bump_trial_length_to_30(apps, schema_editor):
    """
    The product's free trial changed from 14 to 30 days as part of this
    pricing overhaul. Only bumps the singleton TrialSettings row if it is
    still at the OLD seed value (14) - if an admin had already deliberately
    changed it to something else, that deliberate choice is left alone.
    """
    TrialSettings = apps.get_model('billing', 'TrialSettings')
    TrialSettings.objects.filter(pk=1, trial_duration_days=14).update(trial_duration_days=30)


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_subscription_price_ngn'),
        ('referrals', '0002_referralsettings_enabled'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='trialsettings',
            name='trial_duration_days',
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.RunPython(bump_trial_length_to_30, noop_reverse),

        migrations.AlterModelOptions(
            name='pricingsettings',
            options={'verbose_name': 'Pricing settings (deprecated)', 'verbose_name_plural': 'Pricing settings (deprecated)'},
        ),

        migrations.AddField(
            model_name='subscription',
            name='billing_cycle',
            field=models.CharField(blank=True, choices=BILLING_CYCLE_CHOICES, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name='subscription',
            name='trial_phone',
            field=models.CharField(blank=True, db_index=True, default='', max_length=20),
        ),
        migrations.AddField(
            model_name='subscription',
            name='trial_started_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),

        migrations.CreateModel(
            name='PlanPrice',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('billing_cycle', models.CharField(choices=BILLING_CYCLE_CHOICES, max_length=10)),
                ('price_kobo', models.PositiveBigIntegerField(help_text='Price in kobo (1 Naira = 100 kobo). E.g. \u20a65,000 = 500000.')),
                ('currency', models.CharField(default='NGN', max_length=3)),
                ('is_current', models.BooleanField(default=True, help_text='The live price new purchases use for this cycle. Setting this on a new row automatically un-sets it on every older row for the same cycle - existing subscriptions/purchases are entirely unaffected either way.')),
                ('note', models.CharField(blank=True, help_text='Optional internal note, e.g. "Sept 2026 price increase".', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'billing_plan_prices',
                'verbose_name': 'Plan price',
                'verbose_name_plural': 'Plan prices',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='planprice',
            index=models.Index(fields=['billing_cycle', 'is_current'], name='billing_pla_billing_e13f2c_idx'),
        ),

        migrations.CreateModel(
            name='SubscriptionPurchase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('plan', models.CharField(choices=[('FREE', 'Free'), ('PRO', 'Pro')], default='PRO', max_length=10)),
                ('billing_cycle', models.CharField(choices=BILLING_CYCLE_CHOICES, max_length=10)),
                ('amount_paid_kobo', models.PositiveBigIntegerField()),
                ('currency', models.CharField(default='NGN', max_length=3)),
                ('payment_provider', models.CharField(max_length=30)),
                ('payment_reference', models.CharField(max_length=255, unique=True)),
                ('status', models.CharField(choices=[('SUCCESS', 'Success'), ('REFUNDED', 'Refunded'), ('REVERSED', 'Reversed')], default='SUCCESS', max_length=10)),
                ('subscription_start', models.DateTimeField()),
                ('subscription_expiry', models.DateTimeField()),
                ('is_renewal', models.BooleanField(default=False, help_text="False for a user's first-ever successful purchase, True for every purchase after that.")),
                ('refund_reason', models.CharField(blank=True, max_length=255)),
                ('refunded_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan_price', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchases', to='billing.planprice')),
                ('referral', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='subscription_purchases', to='referrals.referral')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subscription_purchases', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'billing_subscription_purchases',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='subscriptionpurchase',
            index=models.Index(fields=['user', 'status'], name='billing_sub_user_id_9d1a55_idx'),
        ),

        migrations.RunPython(seed_plan_prices, noop_reverse),
    ]
