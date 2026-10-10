import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0002_referralsettings_enabled'),
        ('billing', '0007_billing_pricing_overhaul'),
    ]

    operations = [
        # The referral program now pays ONE TIME (from the referred user's
        # first successful paid subscription only) rather than for a
        # capped number of recurring months - see spec \u00a74/\u00a75 and
        # apps.referrals.services.process_referral_commission. cap_months
        # no longer means anything.
        migrations.RemoveField(
            model_name='referralsettings',
            name='cap_months',
        ),
        migrations.AlterField(
            model_name='referralsettings',
            name='commission_percent',
            field=models.DecimalField(
                decimal_places=2, default='20.00', max_digits=5,
                help_text="% of the referred user's FIRST successful paid subscription that the referrer earns. "
                          "This is a ONE-TIME commission, not recurring - a referred user's second purchase, "
                          "renewal, or upgrade never generates a further commission for the same referral. "
                          "See apps/referrals/services.py::process_referral_commission.",
            ),
        ),

        migrations.RemoveField(
            model_name='referralcommission',
            name='month_number',
        ),
        migrations.AddField(
            model_name='referralcommission',
            name='subscription_purchase',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='referral_commissions', to='billing.subscriptionpurchase',
            ),
        ),
        migrations.AddField(
            model_name='referralcommission',
            name='reversed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='referralcommission',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending (no payout account yet)'),
                    ('PROCESSING', 'Transfer initiated'),
                    ('PAID', 'Paid'),
                    ('FAILED', 'Failed'),
                    ('REVERSED', 'Reversed (source payment refunded)'),
                ],
                default='PENDING', max_length=12,
            ),
        ),
    ]
