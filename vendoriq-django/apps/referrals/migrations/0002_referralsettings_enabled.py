from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='referralsettings',
            name='enabled',
            field=models.BooleanField(
                default=True,
                help_text='Master switch for the whole referral program. Turning this off stops NEW referral '
                           'signups and NEW commissions from being created everywhere in the app (registration '
                           'form, Google sign-up, and every Pro payment) - it does NOT stop already-earned '
                           'commissions from being paid out; money already owed to a referrer keeps processing '
                           'normally. See apps/referrals/services.py for exactly where this is checked.',
            ),
        ),
    ]
