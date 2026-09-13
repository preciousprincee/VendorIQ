from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_trialsettings'),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pro_price_ngn', models.PositiveIntegerField(default=5000)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'billing_pricing_settings',
                'verbose_name': 'Pricing settings',
                'verbose_name_plural': 'Pricing settings',
            },
        ),
    ]
