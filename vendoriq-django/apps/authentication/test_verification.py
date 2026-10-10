import re
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail

from apps.authentication.models import User, VerificationCode
from apps.authentication.sms import SMSError

SEND_EMAIL = '/api/auth/verify/email/send/'
CONFIRM_EMAIL = '/api/auth/verify/email/confirm/'
SEND_PHONE = '/api/auth/verify/phone/send/'
CONFIRM_PHONE = '/api/auth/verify/phone/confirm/'


def _code_from(text):
    return re.search(r'\b(\d{6})\b', text).group(1)


@pytest.fixture
def sms_outbox():
    sent = []
    with patch('apps.authentication.verification.sms.send_sms', side_effect=lambda phone, msg: sent.append((phone, msg))):
        yield sent


def _clear_cooldown(user, channel):
    # Move the previous code into the past so the resend cooldown doesn't get in the way.
    from datetime import timedelta
    from django.utils import timezone
    VerificationCode.objects.filter(user=user, channel=channel).update(created_at=timezone.now() - timedelta(minutes=5))


@pytest.mark.django_db
class TestEmailVerification:
    def test_full_flow(self, owner_client, owner_user):
        assert owner_client.post(SEND_EMAIL).status_code == 200
        code = _code_from(mail.outbox[-1].body)
        response = owner_client.post(CONFIRM_EMAIL, {'code': code}, format='json')
        assert response.status_code == 200
        owner_user.refresh_from_db()
        assert owner_user.email_verified is True

    def test_wrong_code_is_rejected_and_locks_after_five_guesses(self, owner_client, owner_user):
        owner_client.post(SEND_EMAIL)
        real = _code_from(mail.outbox[-1].body)
        wrong = '000000' if real != '000000' else '111111'
        for _ in range(5):
            assert owner_client.post(CONFIRM_EMAIL, {'code': wrong}, format='json').status_code == 400
        # Locked: even the CORRECT code no longer works - a 6-digit code is only safe because of this.
        response = owner_client.post(CONFIRM_EMAIL, {'code': real}, format='json')
        assert response.status_code == 400
        owner_user.refresh_from_db()
        assert owner_user.email_verified is False

    def test_resend_cooldown(self, owner_client):
        assert owner_client.post(SEND_EMAIL).status_code == 200
        second = owner_client.post(SEND_EMAIL)
        assert second.status_code == 429
        assert second.data['retryAfter'] > 0

    def test_new_code_invalidates_the_previous_one(self, owner_client, owner_user):
        owner_client.post(SEND_EMAIL)
        first = _code_from(mail.outbox[-1].body)
        _clear_cooldown(owner_user, 'EMAIL')
        owner_client.post(SEND_EMAIL)
        second = _code_from(mail.outbox[-1].body)
        if first != second:
            assert owner_client.post(CONFIRM_EMAIL, {'code': first}, format='json').status_code == 400
        assert owner_client.post(CONFIRM_EMAIL, {'code': second}, format='json').status_code == 200

    def test_code_is_not_stored_in_plaintext(self, owner_client, owner_user):
        owner_client.post(SEND_EMAIL)
        code = _code_from(mail.outbox[-1].body)
        row = VerificationCode.objects.get(user=owner_user)
        assert code not in row.code_hash and len(row.code_hash) == 64


@pytest.mark.django_db
class TestPhoneVerification:
    def test_full_flow_sets_the_number_and_verifies_it(self, owner_client, owner_user, sms_outbox):
        response = owner_client.post(SEND_PHONE, {'phone': '+234 801 234 5678'}, format='json')
        assert response.status_code == 200
        assert sms_outbox[-1][0] == '08012345678'
        code = _code_from(sms_outbox[-1][1])
        assert owner_client.post(CONFIRM_PHONE, {'code': code}, format='json').status_code == 200
        owner_user.refresh_from_db()
        assert owner_user.phone_verified is True and owner_user.referral_code == '08012345678'

    def test_invalid_number_is_rejected_without_sending(self, owner_client, sms_outbox):
        assert owner_client.post(SEND_PHONE, {'phone': '12345'}, format='json').status_code == 400
        assert sms_outbox == []

    def test_no_number_on_account_asks_for_one(self, owner_client, sms_outbox):
        assert owner_client.post(SEND_PHONE, {}, format='json').status_code == 400

    def test_code_for_an_old_number_cannot_verify_a_new_one(self, owner_client, owner_user, sms_outbox):
        owner_client.post(SEND_PHONE, {'phone': '08011112222'}, format='json')
        old_code = _code_from(sms_outbox[-1][1])
        _clear_cooldown(owner_user, 'PHONE')
        owner_client.post(SEND_PHONE, {'phone': '08033334444'}, format='json')  # typo fixed
        # The old code was bound to the old number.
        assert owner_client.post(CONFIRM_PHONE, {'code': old_code}, format='json').status_code in (400,)
        owner_user.refresh_from_db()
        assert owner_user.phone_verified is False

    def test_fixing_a_typo_does_not_wait_out_the_resend_cooldown(self, owner_client, sms_outbox):
        assert owner_client.post(SEND_PHONE, {'phone': '08011112222'}, format='json').status_code == 200
        # Same number again straight away: still rate limited.
        assert owner_client.post(SEND_PHONE, {}, format='json').status_code == 429
        # A DIFFERENT number (the typo fix) goes through immediately.
        assert owner_client.post(SEND_PHONE, {'phone': '08033334444'}, format='json').status_code == 200
        assert sms_outbox[-1][0] == '08033334444'

    def test_number_verified_by_someone_else_is_refused(self, owner_client, other_owner_user, sms_outbox):
        other_owner_user.phone = '08012345678'
        other_owner_user.phone_verified = True
        other_owner_user.save()
        response = owner_client.post(SEND_PHONE, {'phone': '08012345678'}, format='json')
        assert response.status_code == 400
        assert sms_outbox == []

    def test_sms_provider_failure_is_reported_and_does_not_burn_the_cooldown(self, owner_client, owner_user):
        with patch('apps.authentication.verification.sms.send_sms', side_effect=SMSError('down')):
            assert owner_client.post(SEND_PHONE, {'phone': '08011112222'}, format='json').status_code == 502
        with patch('apps.authentication.verification.sms.send_sms') as ok:
            assert owner_client.post(SEND_PHONE, {}, format='json').status_code == 200
            ok.assert_called_once()

    def test_a_number_cannot_be_used_to_spam_someone_across_accounts(self, owner_client, owner_user, sms_outbox):
        from django.utils import timezone
        for i in range(6):
            VerificationCode.objects.create(
                user=owner_user, channel='PHONE', target='08055556666', code_hash='x' * 64,
                expires_at=timezone.now(),
            )
        # Age them past the per-user resend cooldown/hourly cap so it is the
        # per-NUMBER daily cap that answers.
        VerificationCode.objects.update(created_at=timezone.now() - timedelta(hours=2))
        response = owner_client.post(SEND_PHONE, {'phone': '08055556666'}, format='json')
        assert response.status_code == 429
        assert sms_outbox == []


@pytest.mark.django_db
class TestVerificationGatesBilling:
    def test_trial_requires_both_verified(self, owner_client, owner_user):
        response = owner_client.post('/api/billing/trial/start/')
        assert response.status_code == 403
        assert response.data['code'] == 'verification_required'

        owner_user.email_verified = True
        owner_user.save(update_fields=['email_verified'])
        assert owner_client.post('/api/billing/trial/start/').status_code == 403  # phone still missing

        owner_user.phone = '08012345678'
        owner_user.phone_verified = True
        owner_user.save()
        assert owner_client.post('/api/billing/trial/start/').status_code == 200

    def test_checkout_requires_verification(self, owner_client, settings):
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        settings.PAYSTACK_PUBLIC_KEY = 'pk_test_x'
        response = owner_client.post('/api/billing/paystack/initialize/', {'billing_cycle': 'MONTHLY'}, format='json')
        assert response.status_code == 403
        assert response.data['code'] == 'verification_required'
