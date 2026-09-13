from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_subscription_is_complimentary'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='trial_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='subscription',
            name='has_used_trial',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE', 'Active'),
                    ('TRIAL', 'Trial'),
                    ('CANCELLED', 'Cancelled'),
                    ('EXPIRED', 'Expired'),
                    ('PAST_DUE', 'Past due'),
                ],
                default='ACTIVE',
                max_length=10,
            ),
        ),
    ]
