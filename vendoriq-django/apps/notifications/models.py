import uuid

from django.db import models

from apps.authentication.models import User


def validate_internal_link(value):
    """
    Notification links are in-app paths ("/subscription"), never external
    URLs - an admin typo (or a compromised admin account) must not be able to
    turn the bell into a phishing redirect. "//evil.com" is protocol-relative,
    so it is rejected too.
    """
    from django.core.exceptions import ValidationError
    if value and (not value.startswith('/') or value.startswith('//') or '://' in value or '\\' in value):
        raise ValidationError('Use an in-app path such as /subscription or /products (it must start with a single "/").')


class Announcement(models.Model):
    """
    A message the VendorIQ team sends to EVERY user - created from Django
    Admin (Notifications > Announcements > Add). It shows up in each user's
    notification bell with an unread badge until they open the bell.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    message = models.TextField(max_length=500, help_text='Up to 500 characters. Plain text.')
    link = models.CharField(
        max_length=200, blank=True, validators=[validate_internal_link],
        help_text='Optional in-app page to open when tapped, e.g. /subscription. Leave blank for none.',
    )
    is_active = models.BooleanField(default=True, help_text='Untick to withdraw it from everyone\'s bell.')
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Optional - stops showing after this time.')
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notification_announcements'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Notification(models.Model):
    """A notification addressed to ONE user (subscription reminders and the like)."""

    class Kind(models.TextChoices):
        TRIAL_ENDING = 'trial_ending', 'Trial ending'
        SUBSCRIPTION_EXPIRING = 'subscription_expiring', 'Subscription expiring'
        SUBSCRIPTION_EXPIRED = 'subscription_expired', 'Subscription expired'
        DELETION_REQUEST = 'deletion_request', 'Product deletion request'
        DELETION_DECISION = 'deletion_decision', 'Product deletion decision'
        GENERAL = 'general', 'General'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.GENERAL)
    severity = models.CharField(max_length=10, default='medium')
    title = models.CharField(max_length=120)
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True, validators=[validate_internal_link])
    # Makes generation idempotent: "trial-ending:20260930:2" can only ever be
    # created once per user, however many times the bell is polled.
    dedupe_key = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'dedupe_key'], name='notifications_user_dedupe_uniq'),
        ]

    def __str__(self):
        return f'{self.user.email}: {self.title}'


class NotificationSeen(models.Model):
    """
    When this user last opened the bell. Everything newer than this counts as
    unread; opening the bell moves it to "now", which is what clears the
    number on the icon.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name='notification_seen')
    seen_at = models.DateTimeField()

    class Meta:
        db_table = 'notification_seen'
