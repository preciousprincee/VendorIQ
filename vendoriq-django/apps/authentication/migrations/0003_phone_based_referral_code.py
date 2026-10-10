from django.db import migrations, models


def phone_to_referral_code(apps, schema_editor):
    """
    Referral codes are now users' phone numbers (canonical 0XXXXXXXXXX
    form). Old random codes are cleared first, then each user with a valid
    phone gets theirs - oldest account first, so if two existing accounts
    ever shared a number the original owner keeps the code and the later
    one is left without (they can pick a different number in Settings).
    Users with no valid phone end up with NULL and simply have no code
    until they add one.
    """
    from apps.authentication.phone import normalize_phone

    User = apps.get_model('authentication', 'User')
    User.objects.update(referral_code=None)
    taken = set()
    for user in User.objects.order_by('created_at').iterator():
        canonical = normalize_phone(user.phone)
        if canonical and canonical not in taken:
            taken.add(canonical)
            User.objects.filter(pk=user.pk).update(phone=canonical, referral_code=canonical)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_user_referral_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='phone_verified',
            field=models.BooleanField(
                default=False,
                help_text='Once True the user can no longer change their phone number themselves (it is their referral code '
                          'and a free-trial anti-abuse key). Set by staff for now - there is no SMS verification flow yet.',
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='referral_code',
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        migrations.RunPython(phone_to_referral_code, migrations.RunPython.noop),
    ]
