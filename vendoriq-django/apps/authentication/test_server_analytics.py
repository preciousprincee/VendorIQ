"""
Server-side analytics (vendoriq/analytics.py): events are emitted at the right moments, exactly once,
identify people by user id only, and can never break a request.
"""
import re
from unittest.mock import patch

import pytest
from django.core import mail

from apps.authentication.models import User
from apps.billing.plans import MONTHLY
from apps.billing.services import create_subscription_purchase
from vendoriq import analytics


class FakePostHog:
    def __init__(self):
        self.events = []

    def capture(self, distinct_id, event, properties):
        self.events.append((distinct_id, event, properties))

    def named(self, name):
        return [e for e in self.events if e[1] == name]


@pytest.fixture
def ph(settings, django_capture_on_commit_callbacks):
    settings.POSTHOG_API_KEY = 'phc_test'
    fake = FakePostHog()
    with patch.object(analytics, '_get_client', return_value=fake):
        yield fake


def _register(client, email='an@example.com', phone='08034440001'):
    return client.post('/api/auth/register/', {'name': 'Ada Lovelace', 'email': email, 'phone': phone, 'password': 'Strongpass123!'}, format='json')


@pytest.mark.django_db
class TestCapture:
    def test_does_nothing_without_a_key(self, settings, api_client):
        settings.POSTHOG_API_KEY = ''
        with patch.object(analytics, '_get_client') as get_client:
            assert _register(api_client).status_code == 201
        get_client.assert_not_called()

    def test_a_failing_posthog_never_breaks_the_request(self, settings, api_client):
        settings.POSTHOG_API_KEY = 'phc_test'

        class Boom:
            def capture(self, **kwargs):
                raise RuntimeError('posthog is down')

        with patch.object(analytics, '_get_client', return_value=Boom()):
            assert _register(api_client).status_code == 201

    def test_personal_properties_are_stripped(self, ph, owner_user, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            analytics.capture(owner_user, 'x', {'email': 'a@b.c', 'phone': '1', 'name': 'n', 'value': 5, 'nothing': None})
        _, _, props = ph.events[0]
        assert props == {'value': 5, 'source': 'server'}

    def test_not_sent_if_the_transaction_rolls_back(self, ph, owner_user):
        from django.db import transaction
        try:
            with transaction.atomic():
                analytics.capture(owner_user, 'ghost')
                raise RuntimeError('roll back')
        except RuntimeError:
            pass
        assert ph.events == []


@pytest.mark.django_db
class TestEvents:
    def test_register_emits_sign_up_with_the_user_id_and_no_personal_data(self, ph, api_client, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            r = _register(api_client)
        user = User.objects.get(email='an@example.com')
        (distinct_id, event, props), = ph.named('sign_up')
        assert r.status_code == 201 and distinct_id == str(user.pk)
        assert props['method'] == 'email' and props['source'] == 'server'
        assert 'an@example.com' not in str(ph.events) and 'Ada' not in str(ph.events) and '0803444' not in str(ph.events)

    def test_a_failed_registration_emits_nothing(self, ph, api_client, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            r = api_client.post('/api/auth/register/', {'name': 'x', 'email': 'bad', 'phone': '1', 'password': 'p'}, format='json')
        assert r.status_code == 400 and ph.events == []

    def test_email_verified_fires_once(self, ph, owner_client, owner_user, django_capture_on_commit_callbacks):
        owner_client.post('/api/auth/verify/email/send/')
        code = re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)
        with django_capture_on_commit_callbacks(execute=True):
            assert owner_client.post('/api/auth/verify/email/confirm/', {'code': code}, format='json').status_code == 200
            assert owner_client.post('/api/auth/verify/email/confirm/', {'code': code}, format='json').status_code == 200   # already verified: no second event
        assert len(ph.named('email_verified')) == 1

    def test_purchase_is_counted_once_even_if_the_webhook_is_redelivered(self, ph, owner_user, django_capture_on_commit_callbacks):
        kwargs = dict(user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000, currency='NGN',
                      payment_provider='paystack', payment_reference='ref-analytics-1')
        with django_capture_on_commit_callbacks(execute=True):
            create_subscription_purchase(**kwargs)
            create_subscription_purchase(**kwargs)
        (distinct_id, _, props), = ph.named('subscription_purchased')
        assert distinct_id == str(owner_user.pk) and props['amount_ngn'] == 5000 and props['is_renewal'] is False
        assert props['$set'] == {'plan': 'PRO'}

    def test_a_mock_upgrade_is_not_a_purchase(self, ph, owner_user, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            create_subscription_purchase(user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000, currency='NGN',
                                         payment_provider='mock', payment_reference='ref-mock-1')
        assert ph.named('subscription_purchased') == []


@pytest.mark.django_db
class TestGoogleSignUp:
    def test_a_double_submitted_google_sign_in_counts_one_sign_up(self, ph, django_capture_on_commit_callbacks):
        from apps.authentication.test_google_new_account import _response_for
        user = User.objects.create_user(email='g-dup@example.com', name='G', password=None)
        with django_capture_on_commit_callbacks(execute=True):
            _response_for(user)
            _response_for(user)
        assert len(ph.named('sign_up')) == 1
        assert ph.named('sign_up')[0][0] == str(user.pk)
