from django.db import migrations


def demote_staff_owners(apps, schema_editor):
    """
    Before this fix (see apps/stores/views.py::StaffListCreateView.post),
    'role' was accepted straight from the request body with no validation
    against the allowed choices - and 'OWNER' is a real value in
    StaffRole.choices, so a Staff row could end up with role='OWNER' even
    though store ownership is Store.owner, a completely separate field;
    OWNER was never meant to be a valid Staff row at all. Any such row
    would have granted that account full owner-level access to the store
    (store deletion, profitability reports, bookkeeping exports,
    subscription/billing management - every allowed_roles=['OWNER'] check
    in the backend) without ever actually being the store's owner.

    This demotes any surviving 'OWNER' Staff rows to 'MANAGER' - the
    highest role that's actually valid for a Staff row, preserving the
    account's day-to-day access to the store while removing the
    unauthorized owner-equivalent bypass. It does NOT touch Store.owner
    itself (the real owner relationship, untouched by the bug this fixes)
    and does not remove the staff member entirely, since demoting rather
    than deleting is the smaller, safer correction when we can't know
    whether the elevated role was a genuine mistake by the actual store
    owner or the exploit this migration exists to clean up after - either
    way, MANAGER is never a security regression from where they legitimately
    should have been.
    """
    Staff = apps.get_model('stores', 'Staff')
    Staff.objects.filter(role='OWNER').update(role='MANAGER')


def noop_reverse(apps, schema_editor):
    # Not reversible - we can't know which of these were manager-eligible
    # vs. cashier-eligible before the demotion, and reversing back to the
    # exploited state would be actively wrong regardless.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(demote_staff_owners, noop_reverse),
    ]
