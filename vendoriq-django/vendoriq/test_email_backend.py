"""Resend email backend: payloads, retries, idempotency and failure behaviour (no network, no database)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.core.mail import EmailMultiAlternatives

from vendoriq import email_backend as eb

CONF = SimpleNamespace(RESEND_API_KEY='re_test_key', EMAIL_TIMEOUT=10, DEFAULT_FROM_EMAIL='VendorIQ <no-reply@example.com>')


def msg(**kw):
    m = EmailMultiAlternatives(kw.pop('subject', 'Hello'), kw.pop('body', 'plain body'), to=kw.pop('to', ['a@example.com']), **kw)
    return m


def resp(status=200, body=None, headers=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body if body is not None else ({'id': 'abc'} if status == 200 else {'name': 'error', 'message': 'nope'})
    r.headers = headers or {}
    r.text = str(body)
    r.content = b'x'
    return r


@pytest.fixture(autouse=True)
def _conf():
    with patch.object(eb, 'settings', CONF), patch.object(eb.time, 'sleep') as sleep:
        yield sleep


class TestPayload:
    def test_text_and_html_and_default_sender(self):
        m = msg(body='plain')
        m.attach_alternative('<b>rich</b>', 'text/html')
        p = eb.build_payload(m, 'VendorIQ <no-reply@example.com>')
        assert p['from'] == 'VendorIQ <no-reply@example.com>' and p['to'] == ['a@example.com']
        assert p['text'] == 'plain' and p['html'] == '<b>rich</b>' and p['subject'] == 'Hello'

    def test_explicit_sender_cc_bcc_reply_to(self):
        m = msg(from_email='Shop <shop@example.com>', cc=['c@example.com'], bcc=['b@example.com'], reply_to=['r@example.com'])
        p = eb.build_payload(m, 'x')
        assert p['from'] == 'Shop <shop@example.com>' and p['cc'] == ['c@example.com']
        assert p['bcc'] == ['b@example.com'] and p['reply_to'] == ['r@example.com']

    def test_html_body_message(self):
        m = msg(body='<p>hi</p>')
        m.content_subtype = 'html'
        p = eb.build_payload(m, 'x')
        assert p['html'] == '<p>hi</p>' and 'text' not in p

    def test_attachments_are_base64(self):
        m = msg()
        m.attach('invoice.pdf', b'%PDF-1.4', 'application/pdf')
        a = eb.build_payload(m, 'x')['attachments'][0]
        assert a['filename'] == 'invoice.pdf' and a['content'] == 'JVBERi0xLjQ='

    def test_an_empty_body_still_sends_something(self):
        assert eb.build_payload(msg(body=''), 'x')['text']


class TestSending:
    def test_success_posts_to_resend_with_auth_and_idempotency_key(self):
        with patch.object(eb.requests, 'post', return_value=resp()) as post:
            assert eb.ResendEmailBackend().send_messages([msg()]) == 1
        assert post.call_args.args[0] == 'https://api.resend.com/emails'
        h = post.call_args.kwargs['headers']
        assert h['Authorization'] == 'Bearer re_test_key' and h['Idempotency-Key']
        assert post.call_args.kwargs['timeout'] == 10

    def test_rate_limit_is_retried_with_the_SAME_idempotency_key(self, _conf):
        with patch.object(eb.requests, 'post', side_effect=[resp(429, headers={'retry-after': '1'}), resp()]) as post:
            assert eb.ResendEmailBackend().send_messages([msg()]) == 1
        keys = [c.kwargs['headers']['Idempotency-Key'] for c in post.call_args_list]
        assert len(keys) == 2 and keys[0] == keys[1]
        _conf.assert_called()                      # it waited between attempts

    def test_a_client_error_is_not_retried_and_says_why(self):
        bad = resp(403, {'name': 'validation_error', 'message': 'The vendoriq.app domain is not verified.'})
        with patch.object(eb.requests, 'post', return_value=bad) as post:
            with pytest.raises(eb.EmailDeliveryError, match='not verified'):
                eb.ResendEmailBackend().send_messages([msg()])
        assert post.call_count == 1

    def test_gives_up_after_three_attempts_on_server_errors(self):
        with patch.object(eb.requests, 'post', return_value=resp(500, {'name': 'x', 'message': 'boom'})) as post:
            with pytest.raises(eb.EmailDeliveryError):
                eb.ResendEmailBackend().send_messages([msg()])
        assert post.call_count == 3

    def test_network_errors_are_retried_then_reported(self):
        with patch.object(eb.requests, 'post', side_effect=requests.exceptions.ConnectTimeout()) as post:
            with pytest.raises(eb.EmailDeliveryError, match='could not reach Resend'):
                eb.ResendEmailBackend().send_messages([msg()])
        assert post.call_count == 3

    def test_fail_silently_returns_zero(self):
        with patch.object(eb.requests, 'post', return_value=resp(401)):
            assert eb.ResendEmailBackend(fail_silently=True).send_messages([msg()]) == 0

    def test_a_200_without_an_id_is_not_a_success(self):
        with patch.object(eb.requests, 'post', return_value=resp(200, {})):
            with pytest.raises(eb.EmailDeliveryError):
                eb.ResendEmailBackend().send_messages([msg()])

    def test_a_missing_key_fails_clearly_without_calling_resend(self):
        with patch.object(eb, 'settings', SimpleNamespace(RESEND_API_KEY='', EMAIL_TIMEOUT=10, DEFAULT_FROM_EMAIL='x@example.com')):
            with patch.object(eb.requests, 'post') as post:
                with pytest.raises(eb.EmailDeliveryError, match='RESEND_API_KEY'):
                    eb.ResendEmailBackend().send_messages([msg()])
        post.assert_not_called()

    def test_several_messages_are_sent_one_by_one(self):
        with patch.object(eb.requests, 'post', return_value=resp()) as post:
            assert eb.ResendEmailBackend().send_messages([msg(), msg(to=['z@example.com'])]) == 2
        assert post.call_count == 2
