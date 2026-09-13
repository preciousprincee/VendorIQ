from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_subscription_trial_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrialSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trial_duration_days', models.PositiveIntegerField(default=14)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'billing_trial_settings',
                'verbose_name': 'Trial settings',
                'verbose_name_plural': 'Trial settings',
            },
        ),
    ]
