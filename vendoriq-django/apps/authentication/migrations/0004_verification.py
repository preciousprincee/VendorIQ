import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def mark_google_only_accounts_email_verified(apps, schema_editor):
    """
    Google-only accounts (no usable password) signed up through Google, which
    has already verified the address - don't make them do it again. Everyone
    else (email + password) is asked to verify on their next login.
    """
    User = apps.get_model('authentication', 'User')
    User.objects.filter(password__startswith='!').update(email_verified=True)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_phone_based_referral_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verified',
            field=models.BooleanField(default=False, help_text='Set when the user enters the code we email them, or automatically for Google sign-in (Google has already verified that address).'),
        ),
        migrations.AlterField(
            model_name='user',
            name='phone_verified',
            field=models.BooleanField(default=False, help_text='Set when the user proves they own the number by entering the SMS code we send (see apps/authentication/verification.py). Once True they can no longer change the number themselves (it is their referral code and a free-trial anti-abuse key).'),
        ),
        migrations.CreateModel(
            name='VerificationCode',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('channel', models.CharField(choices=[('EMAIL', 'Email'), ('PHONE', 'Phone')], max_length=5)),
                ('target', models.CharField(max_length=254)),
                ('code_hash', models.CharField(max_length=64)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('expires_at', models.DateTimeField()),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='verification_codes', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'verification_codes',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', 'channel', 'created_at'], name='verificatio_user_id_ece5cf_idx'),
                    models.Index(fields=['channel', 'target', 'created_at'], name='verificatio_channel_6de6f4_idx'),
                ],
            },
        ),
        migrations.RunPython(mark_google_only_accounts_email_verified, migrations.RunPython.noop),
    ]
