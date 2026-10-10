from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referrals', '0003_referral_one_time_commission'),
    ]

    operations = [
        # Referral codes are phone numbers now (up to 20 chars like the
        # phone column itself), not 7-character random strings.
        migrations.AlterField(
            model_name='referral',
            name='code_used',
            field=models.CharField(max_length=20),
        ),
    ]
