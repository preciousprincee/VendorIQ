"""
Sending an SMS - one function, pluggable provider.

Backends (settings.SMS_BACKEND):
  'termii'  - real delivery through Termii (https://termii.com), the usual
              choice for Nigerian numbers. Needs TERMII_API_KEY and, for
              branded delivery, an approved TERMII_SENDER_ID.
  'console' - prints the message to the server log instead of sending.
              Local development ONLY (DEBUG=True). With DEBUG off it is refused
              here, and settings.py refuses to even start without Termii keys.
"""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def _termii_url():
    # Termii shows the base URL to use on your dashboard (api.ng.termii.com is the default).
    return f"{settings.TERMII_BASE_URL}/api/sms/send"


class SMSError(Exception):
    """The message could not be sent (or we could not tell whether it was)."""


class SMSNotConfigured(SMSError):
    pass


def _international(canonical_phone):
    """0XXXXXXXXXX -> 234XXXXXXXXXX (no '+', which is what Termii expects)."""
    return '234' + canonical_phone[1:]


def sms_backend_name():
    return getattr(settings, 'SMS_BACKEND', 'console')


def send_sms(canonical_phone, message):
    backend = sms_backend_name()
    if backend == 'console':
        if not settings.DEBUG:
            raise SMSNotConfigured('SMS sending is not configured on this server.')
        logger.warning('[SMS console backend] to=%s message=%s', canonical_phone, message)
        return
    if backend == 'termii':
        if not settings.TERMII_API_KEY:
            raise SMSNotConfigured('SMS sending is not configured on this server.')
        try:
            response = requests.post(
                _termii_url(),
                json={
                    'to': _international(canonical_phone),
                    'from': settings.TERMII_SENDER_ID,
                    'sms': message,
                    'type': 'plain',
                    # 'dnd' routes through the DND-capable route so numbers
                    # with promotional-SMS blocking still receive OTPs.
                    'channel': settings.TERMII_CHANNEL,
                    'api_key': settings.TERMII_API_KEY,
                },
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            logger.error('Termii request failed', exc_info=True)
            raise SMSError('Could not reach the SMS provider. Please try again shortly.') from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        # Success = HTTP 200 AND Termii confirming it queued the message: either the older
        # {"code": "ok"} or the current {"message_id": "...", "message": "Successfully Sent"}.
        # A 200 carrying neither (e.g. an error body) must NOT count as sent.
        accepted = str(data.get('code', '')).lower() == 'ok' or bool(data.get('message_id'))
        if response.status_code != 200 or not accepted:
            logger.error('Termii returned %s: %s', response.status_code, response.text[:300])
            raise SMSError('Could not send the SMS. Please try again shortly.')
        return
    raise SMSNotConfigured(f'Unknown SMS_BACKEND {backend!r}.')
