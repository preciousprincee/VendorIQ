"""
Regression tests for the payment-integrity fixes: a payment is only honoured
if it is (a) for a checkout WE started for THIS user and (b) for at least the
price recorded at that moment - never on the strength of browser-supplied
metadata or an arbitrary Paystack reference.
"""
import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

import pytest

from apps.billing.entitlements import get_subscription, start_trial, AlreadyOnProError
from apps.billing.models import CheckoutSession, SubscriptionPurchase
from apps.billing.plans import MONTHLY, ANNUAL, PRO

MONTHLY_KOBO = 500000  # seed price, see TestNewPurchases in tests.py


def _session(user, reference='viq-test-1', cycle=MONTHLY, amount=MONTHLY_KOBO):
    return CheckoutSession.objects.create(
        reference=reference, user=user, billing_cycle=cycle, amount_kobo=amount, currency='NGN',
    )


def _paystack_verify_response(reference, amount, currency='NGN', status='success', metadata=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = ''
    resp.json.return_value = {'status': True, 'data': {
        'status': status, 'reference': reference, 'amount': amount, 'currency': currency,
        'metadata': metadata or {},
    }}
    return resp


@pytest.mark.django_db
class TestVerifyEndpoint:
    def test_unknown_reference_is_rejected(self, owner_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        response = owner_client.post('/api/billing/paystack/verify/', {'reference': 'never-issued'}, format='json')
        assert response.status_code == 403
        assert get_subscription(owner_user).plan != PRO

    def test_someone_elses_reference_is_rejected(self, owner_client, owner_user, other_owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        _session(other_owner_user, reference='viq-theirs')
        response = owner_client.post('/api/billing/paystack/verify/', {'reference': 'viq-theirs'}, format='json')
        assert response.status_code == 403
        assert get_subscription(owner_user).plan != PRO

    def test_malformed_reference_is_rejected_before_any_network_call(self, owner_client, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        with patch('apps.billing.views.requests.get') as mock_get:
            for bad in ('../../transfer', 'a/b', 'x?y=1', '', None, 123, ['a']):
                response = owner_client.post('/api/billing/paystack/verify/', {'reference': bad}, format='json')
                assert response.status_code == 400
            mock_get.assert_not_called()

    def test_underpayment_does_not_activate_pro(self, owner_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        _session(owner_user, reference='viq-cheap', cycle=ANNUAL, amount=4800000)
        # Browser paid NGN 50 but claims ANNUAL in metadata.
        fake = _paystack_verify_response('viq-cheap', amount=5000, metadata={'billing_cycle': 'ANNUAL'})
        with patch('apps.billing.views.requests.get', return_value=fake):
            response = owner_client.post('/api/billing/paystack/verify/', {'reference': 'viq-cheap'}, format='json')
        assert response.status_code == 400
        assert get_subscription(owner_user).plan != PRO
        assert not SubscriptionPurchase.objects.filter(user=owner_user).exists()

    def test_wrong_currency_is_rejected(self, owner_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        _session(owner_user, reference='viq-usd')
        fake = _paystack_verify_response('viq-usd', amount=MONTHLY_KOBO, currency='USD')
        with patch('apps.billing.views.requests.get', return_value=fake):
            response = owner_client.post('/api/billing/paystack/verify/', {'reference': 'viq-usd'}, format='json')
        assert response.status_code == 400
        assert get_subscription(owner_user).plan != PRO

    def test_correct_payment_activates_pro_using_the_sessions_cycle_not_metadata(self, owner_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        _session(owner_user, reference='viq-ok')  # MONTHLY session
        fake = _paystack_verify_response('viq-ok', amount=MONTHLY_KOBO, metadata={'billing_cycle': 'ANNUAL'})
        with patch('apps.billing.views.requests.get', return_value=fake):
            response = owner_client.post('/api/billing/paystack/verify/', {'reference': 'viq-ok'}, format='json')
        assert response.status_code == 200
        purchase = SubscriptionPurchase.objects.get(user=owner_user)
        assert purchase.billing_cycle == MONTHLY  # NOT the ANNUAL the metadata claimed
        assert get_subscription(owner_user).plan == PRO


def _signed_post(client, settings, payload):
    body = json.dumps(payload).encode()
    sig = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest()
    return client.post('/api/billing/paystack-webhook/', data=body, content_type='application/json', HTTP_X_PAYSTACK_SIGNATURE=sig)


@pytest.mark.django_db
class TestChargeWebhook:
    def test_charge_without_a_checkout_session_is_ignored(self, api_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        response = _signed_post(api_client, settings, {'event': 'charge.success', 'data': {
            'reference': 'someone-elses-product', 'amount': MONTHLY_KOBO, 'currency': 'NGN', 'status': 'success',
            'metadata': {'user_id': str(owner_user.id), 'billing_cycle': 'ANNUAL'},
        }})
        assert response.status_code == 200
        assert not SubscriptionPurchase.objects.filter(user=owner_user).exists()

    def test_underpaid_charge_is_not_honoured(self, api_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        _session(owner_user, reference='viq-wh-cheap', cycle=ANNUAL, amount=4800000)
        _signed_post(api_client, settings, {'event': 'charge.success', 'data': {
            'reference': 'viq-wh-cheap', 'amount': 100, 'currency': 'NGN', 'status': 'success',
            'metadata': {'user_id': str(owner_user.id), 'billing_cycle': 'ANNUAL'},
        }})
        assert not SubscriptionPurchase.objects.filter(user=owner_user).exists()

    def test_valid_charge_creates_exactly_one_purchase_even_if_redelivered(self, api_client, owner_user, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        _session(owner_user, reference='viq-wh-ok')
        payload = {'event': 'charge.success', 'data': {
            'reference': 'viq-wh-ok', 'amount': MONTHLY_KOBO, 'currency': 'NGN', 'status': 'success',
        }}
        assert _signed_post(api_client, settings, payload).status_code == 200
        assert _signed_post(api_client, settings, payload).status_code == 200
        assert SubscriptionPurchase.objects.filter(user=owner_user).count() == 1

    def test_bad_signature_is_rejected(self, api_client, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        response = api_client.post('/api/billing/paystack-webhook/', data=b'{}', content_type='application/json', HTTP_X_PAYSTACK_SIGNATURE='nope')
        assert response.status_code == 401


@pytest.mark.django_db
class TestTrialCannotClobberPaidPro:
    def test_start_trial_refuses_an_account_that_already_has_paid_pro(self, owner_user):
        from apps.billing.services import create_subscription_purchase
        create_subscription_purchase(
            user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=4800000, currency='NGN',
            payment_provider='paystack', payment_reference='ref-trial-guard',
        )
        before = get_subscription(owner_user).current_period_end
        with pytest.raises(AlreadyOnProError):
            start_trial(owner_user)
        sub = get_subscription(owner_user)
        assert sub.current_period_end == before
        assert sub.billing_cycle == ANNUAL
