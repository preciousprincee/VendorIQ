"""
Live mode: verification codes are only ever DELIVERED (email / SMS), never echoed back to the browser,
and a provider reply that is not a clear "accepted" is never treated as sent.
"""
from unittest.mock import MagicMock, patch

import pytest

from apps.authentication import sms


def _resp(status, body):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    r.text = str(body)
    return r


@pytest.fixture
def termii(settings):
    settings.SMS_BACKEND = 'termii'
    settings.TERMII_API_KEY = 'TLxxxx'
    settings.TERMII_BASE_URL = 'https://api.ng.termii.com'
    settings.TERMII_SENDER_ID = 'N-Alert'
    settings.TERMII_CHANNEL = 'dnd'


class TestTermiiResponses:
    def test_current_success_shape_counts_as_sent(self, termii):
        with patch('apps.authentication.sms.requests.post', return_value=_resp(200, {'message_id': '123', 'message': 'Successfully Sent', 'balance': 11.5})) as post:
            sms.send_sms('08012345678', 'hi')
        assert post.call_args.args[0] == 'https://api.ng.termii.com/api/sms/send'
        assert post.call_args.kwargs['json']['to'] == '2348012345678'

    def test_older_success_shape_counts_as_sent(self, termii):
        with patch('apps.authentication.sms.requests.post', return_value=_resp(200, {'code': 'ok', 'message': 'Successfully Sent'})):
            sms.send_sms('08012345678', 'hi')

    def test_a_200_with_an_error_body_is_NOT_sent(self, termii):
        with patch('apps.authentication.sms.requests.post', return_value=_resp(200, {'message': 'Insufficient balance'})):
            with pytest.raises(sms.SMSError):
                sms.send_sms('08012345678', 'hi')

    def test_a_rejected_key_is_not_sent(self, termii):
        with patch('apps.authentication.sms.requests.post', return_value=_resp(401, {'message': 'Invalid API key'})):
            with pytest.raises(sms.SMSError):
                sms.send_sms('08012345678', 'hi')

    def test_the_base_url_is_configurable(self, termii, settings):
        settings.TERMII_BASE_URL = 'https://v3.api.termii.com'
        with patch('apps.authentication.sms.requests.post', return_value=_resp(200, {'message_id': '1'})) as post:
            sms.send_sms('08012345678', 'hi')
        assert post.call_args.args[0] == 'https://v3.api.termii.com/api/sms/send'

    def test_the_console_backend_is_refused_outside_debug(self, settings):
        settings.SMS_BACKEND = 'console'
        settings.DEBUG = False
        with pytest.raises(sms.SMSNotConfigured):
            sms.send_sms('08012345678', 'hi')


@pytest.mark.django_db
class TestCodesAreNeverEchoed:
    def test_email_send_does_not_return_the_code_even_in_debug(self, settings, owner_client):
        settings.DEBUG = True
        r = owner_client.post('/api/auth/verify/email/send/')
        assert r.status_code == 200
        assert 'debugCode' not in r.json()

    def test_phone_send_does_not_return_the_code_even_in_debug(self, settings, owner_client):
        settings.DEBUG = True
        settings.SMS_BACKEND = 'console'
        r = owner_client.post('/api/auth/verify/phone/send/', {'phone': '08012345678'}, format='json')
        assert r.status_code == 200
        assert 'debugCode' not in r.json()
