import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.notifications.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=120)),
                ('message', models.TextField(help_text='Up to 500 characters. Plain text.', max_length=500)),
                ('link', models.CharField(blank=True, help_text='Optional in-app page to open when tapped, e.g. /subscription. Leave blank for none.', max_length=200, validators=[apps.notifications.models.validate_internal_link])),
                ('is_active', models.BooleanField(default=True, help_text="Untick to withdraw it from everyone's bell.")),
                ('expires_at', models.DateTimeField(blank=True, help_text='Optional - stops showing after this time.', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'notification_announcements', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('trial_ending', 'Trial ending'), ('subscription_expiring', 'Subscription expiring'), ('subscription_expired', 'Subscription expired'), ('general', 'General')], default='general', max_length=30)),
                ('severity', models.CharField(default='medium', max_length=10)),
                ('title', models.CharField(max_length=120)),
                ('message', models.TextField()),
                ('link', models.CharField(blank=True, max_length=200, validators=[apps.notifications.models.validate_internal_link])),
                ('dedupe_key', models.CharField(max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'notifications', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='NotificationSeen',
            fields=[
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='notification_seen', serialize=False, to=settings.AUTH_USER_MODEL)),
                ('seen_at', models.DateTimeField()),
            ],
            options={'db_table': 'notification_seen'},
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(fields=('user', 'dedupe_key'), name='notifications_user_dedupe_uniq'),
        ),
    ]
