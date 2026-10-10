import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class CreateModelIfMissing(migrations.CreateModel):
    """
    CreateModel that does nothing to the DATABASE when the table is already there (the model is still
    registered in migration state).

    Why: LoginEvent existed in models.py (login history, brute-force lockout) but no earlier migration created
    its table, so a fresh database had no `login_events` table and every login/registration answered 500.
    A database that was set up another way may already HAVE the table; this migration must work for both.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        if model._meta.db_table in schema_editor.connection.introspection.table_names():
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0004_verification'),
    ]

    operations = [
        CreateModelIfMissing(
            name='LoginEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email_attempted', models.EmailField(max_length=254)),
                ('success', models.BooleanField(default=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('device_type', models.CharField(blank=True, max_length=20)),
                ('browser', models.CharField(blank=True, max_length=50)),
                ('os', models.CharField(blank=True, max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='login_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'login_events',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['user', 'created_at'], name='login_event_user_id_df2f7e_idx'),
                    models.Index(fields=['email_attempted', 'created_at'], name='login_event_email_a_037f5e_idx'),
                ],
            },
        ),
    ]
