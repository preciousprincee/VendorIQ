from django.db import migrations, models


def backfill_referral_codes(apps, schema_editor):
    """
    AddField with a single shared default ('') then AlterField straight to
    unique=True would leave every EXISTING user with the same blank code
    fighting over one unique slot - fine for a fresh dev DB with zero rows,
    a real problem the moment there's more than one existing user. Give
    each existing row its own code first, then lock in uniqueness below.
    """
    User = apps.get_model('authentication', 'User')
    # Import the real generator rather than reimplementing it here so this
    # migration can never drift from apps/authentication/models.py's
    # definition of what a valid code looks like.
    from apps.authentication.models import generate_referral_code

    for user in User.objects.filter(referral_code=''):
        for _ in range(5):
            candidate = generate_referral_code()
            if not User.objects.filter(referral_code=candidate).exists():
                user.referral_code = candidate
                user.save(update_fields=['referral_code'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='referral_code',
            field=models.CharField(blank=True, max_length=12, default=''),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_referral_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='referral_code',
            field=models.CharField(blank=True, max_length=12, unique=True),
        ),
    ]
