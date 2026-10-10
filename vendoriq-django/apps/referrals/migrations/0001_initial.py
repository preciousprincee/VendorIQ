import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('authentication', '0002_user_referral_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReferralSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('commission_percent', models.DecimalField(decimal_places=2, default='20.00', help_text="% of the referred user's payment the referrer earns, each eligible month.", max_digits=5)),
                ('cap_months', models.PositiveIntegerField(default=12, help_text='How many of the referred user\'s paid months earn a commission. After this many, referrals from this pair stop generating commissions.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'referral_settings',
                'verbose_name': 'Referral settings',
                'verbose_name_plural': 'Referral settings',
            },
        ),
        migrations.CreateModel(
            name='PayoutAccount',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bank_code', models.CharField(max_length=10)),
                ('bank_name', models.CharField(max_length=100)),
                ('account_number', models.CharField(max_length=20)),
                ('account_name', models.CharField(max_length=255)),
                ('paystack_recipient_code', models.CharField(blank=True, max_length=100)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='payout_account', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'referral_payout_accounts',
            },
        ),
        migrations.CreateModel(
            name='Referral',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_used', models.CharField(max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('referred_user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='referred_by_record', to=settings.AUTH_USER_MODEL)),
                ('referrer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='referrals_made', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'referrals',
            },
        ),
        migrations.CreateModel(
            name='ReferralCommission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month_number', models.PositiveIntegerField(help_text="Which of the referred user's paid months this is (1-based) - enforces the cap.")),
                ('source_reference', models.CharField(max_length=100)),
                ('amount_ngn', models.DecimalField(decimal_places=2, max_digits=10)),
                ('status', models.CharField(choices=[('PENDING', 'Pending (no payout account yet)'), ('PROCESSING', 'Transfer initiated'), ('PAID', 'Paid'), ('FAILED', 'Failed')], default='PENDING', max_length=12)),
                ('paystack_transfer_code', models.CharField(blank=True, max_length=100)),
                ('failure_reason', models.CharField(blank=True, max_length=255)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('referral', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='commissions', to='referrals.referral')),
            ],
            options={
                'db_table': 'referral_commissions',
                'ordering': ['-created_at'],
                'unique_together': {('referral', 'source_reference')},
            },
        ),
    ]
