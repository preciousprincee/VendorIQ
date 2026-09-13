from django.db import migrations, models


def backfill_price_ngn(apps, schema_editor):
    """
    Existing paying Pro subscribers (created before price_ngn existed) get
    the CURRENT Pro price as their locked-in price - the best available
    approximation of what they're actually paying, since there's no
    historical payment ledger to check against (the upgrade flow is
    mocked). This only matters if PricingSettings has already been changed
    since these subscriptions were created; for everyone else it's exactly
    correct. Trial, complimentary, and non-Pro subscriptions are left at
    the field's default of 0, since none of those represent real payment.
    """
    Subscription = apps.get_model('billing', 'Subscription')
    PricingSettings = apps.get_model('billing', 'PricingSettings')

    pricing = PricingSettings.objects.filter(pk=1).first()
    current_price = pricing.pro_price_ngn if pricing else 5000

    Subscription.objects.filter(
        plan='PRO',
        is_complimentary=False,
        status__in=['ACTIVE', 'CANCELLED'],
    ).update(price_ngn=current_price)


def noop_reverse(apps, schema_editor):
    # Nothing to undo - reversing this migration just means going back to
    # everyone showing price_ngn=0, which is the AddField's own default.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0005_pricingsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='price_ngn',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_price_ngn, noop_reverse),
    ]
