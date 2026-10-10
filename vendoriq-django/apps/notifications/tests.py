from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.entitlements import get_subscription
from apps.billing.models import SubscriptionStatus
from apps.billing.plans import PRO
from apps.notifications.models import Announcement, Notification


@pytest.mark.django_db
class TestBellAndAnnouncements:
    def test_announcement_reaches_a_user_and_badge_clears_after_opening(self, owner_client):
        Announcement.objects.create(title='Maintenance', message='Sunday 2am downtime.')
        data = owner_client.get('/api/notifications/').data
        assert data['unreadCount'] == 1
        assert data['notifications'][0]['title'] == 'Maintenance'

        owner_client.post('/api/notifications/seen/')
        data = owner_client.get('/api/notifications/').data
        assert data['unreadCount'] == 0
        assert len(data['notifications']) == 1  # still listed, just read

        Announcement.objects.create(title='New feature', message='Try it.')
        assert owner_client.get('/api/notifications/').data['unreadCount'] == 1

    def test_withdrawn_and_expired_announcements_are_hidden(self, owner_client):
        Announcement.objects.create(title='gone', message='x', is_active=False)
        Announcement.objects.create(title='old', message='x', expires_at=timezone.now() - timedelta(hours=1))
        assert owner_client.get('/api/notifications/').data['notifications'] == []

    def test_cashier_sees_announcements_but_not_store_alerts(self, cashier_client, store):
        from apps.products.models import Product
        Product.objects.create(store=store, name='Empty', cost_price='1', selling_price='2', quantity=0)
        Announcement.objects.create(title='Hello all', message='x')
        titles = [n.get('title') or n['message'] for n in cashier_client.get(f'/api/notifications/?store={store.id}').data['notifications']]
        assert titles == ['Hello all']

    def test_owner_gets_store_alerts_merged_in(self, owner_client, store):
        from apps.products.models import Product
        Product.objects.create(store=store, name='Empty', cost_price='1', selling_price='2', quantity=0)
        messages = [n['message'] for n in owner_client.get(f'/api/notifications/?store={store.id}').data['notifications']]
        assert any('Empty is out of stock' in m for m in messages)

    def test_bad_store_param_is_ignored_not_a_500(self, owner_client):
        assert owner_client.get('/api/notifications/?store=not-a-uuid').status_code == 200

    def test_requires_login(self, api_client):
        assert api_client.get('/api/notifications/').status_code == 401


@pytest.mark.django_db
class TestSubscriptionReminders:
    def _paid_until(self, user, days):
        sub = get_subscription(user)
        sub.plan = PRO
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_end = timezone.now() + timedelta(days=days, hours=1)
        sub.is_complimentary = False
        sub.save()

    def test_expiring_plan_creates_one_reminder_no_matter_how_often_polled(self, owner_client, owner_user):
        self._paid_until(owner_user, 2)
        for _ in range(4):
            owner_client.get('/api/notifications/')
        assert Notification.objects.filter(user=owner_user, kind='subscription_expiring').count() == 1

    def test_plan_far_from_expiry_gets_no_reminder(self, owner_client, owner_user):
        self._paid_until(owner_user, 40)
        owner_client.get('/api/notifications/')
        assert not Notification.objects.filter(user=owner_user).exists()

    def test_free_user_gets_no_reminder(self, owner_client, owner_user):
        owner_client.get('/api/notifications/')
        assert not Notification.objects.filter(user=owner_user).exists()

    def test_trial_ending_reminder(self, owner_client, owner_user):
        from apps.billing.entitlements import start_trial
        from apps.billing.models import get_trial_period_days
        start_trial(owner_user)
        sub = get_subscription(owner_user)
        sub.trial_started_at = timezone.now() - timedelta(days=get_trial_period_days() - 1, hours=12)
        sub.save()
        owner_client.get('/api/notifications/')
        assert Notification.objects.filter(user=owner_user, kind='trial_ending').count() == 1

    def test_each_user_only_sees_their_own_reminders(self, owner_client, owner_user, other_owner_client, other_owner_user):
        self._paid_until(owner_user, 2)
        owner_client.get('/api/notifications/')
        other = other_owner_client.get('/api/notifications/').data['notifications']
        assert other == []


@pytest.mark.django_db
class TestAnnouncementLinkValidation:
    def test_external_links_are_rejected(self):
        from django.core.exceptions import ValidationError
        from apps.notifications.models import validate_internal_link
        for bad in ('https://evil.com', '//evil.com', 'javascript:alert(1)', 'evil.com', '/ok\\..'):
            with pytest.raises(ValidationError):
                validate_internal_link(bad)
        validate_internal_link('/subscription')
        validate_internal_link('')


@pytest.mark.django_db
class TestBellEdgeCases:
    def test_announcement_from_before_signup_is_not_shown_to_a_new_user(self, owner_client, owner_user):
        Announcement.objects.create(title='Old news', message='x')
        Announcement.objects.update(created_at=owner_user.created_at - timedelta(days=3))
        data = owner_client.get('/api/notifications/').data
        assert data['notifications'] == [] and data['unreadCount'] == 0

    def test_newly_overdue_invoice_is_unread_even_if_the_bell_was_opened_recently(self, owner_client, owner_user, store):
        from apps.invoices.models import Invoice
        from apps.notifications.models import NotificationSeen
        now = timezone.now()
        # Became overdue (14 days old) one hour ago; the bell was last opened two hours ago.
        fresh = Invoice.objects.create(store=store, customer_name='Fresh', status='SENT', total_amount=100)
        Invoice.objects.filter(pk=fresh.pk).update(created_at=now - timedelta(days=14, hours=1))
        # Overdue for five days already - the person has long known about this one.
        old = Invoice.objects.create(store=store, customer_name='Old', status='SENT', total_amount=100)
        Invoice.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=19))
        NotificationSeen.objects.create(user=owner_user, seen_at=now - timedelta(hours=2))

        data = owner_client.get(f'/api/notifications/?store={store.id}').data
        unread = [n['message'] for n in data['notifications'] if n['unread']]
        assert data['unreadCount'] == 1
        assert len(unread) == 1 and 'Fresh' in unread[0]
