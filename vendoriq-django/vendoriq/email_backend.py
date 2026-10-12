"""
Django email backend for Resend (https://resend.com), using its HTTPS API.

Why the API rather than SMTP: no ports to open or TLS modes to get wrong, a hard timeout we control,
and precise error messages ("domain is not verified") instead of generic SMTP failures.

Selected in settings.py when RESEND_API_KEY is set:  EMAIL_BACKEND = 'vendoriq.email_backend.ResendEmailBackend'
Everything that sends mail (verification codes, invoices) keeps using Django's normal send_mail /
EmailMultiAlternatives - only the delivery mechanism changes.

Behaviour worth knowing:
  * The "from" address must be on a domain verified in your Resend account (or Resend rejects it).
  * Each message carries an Idempotency-Key, so retrying after a timeout can never deliver it twice.
  * 429 (rate limited) and 5xx are retried a couple of times with a short wait; 4xx (bad key, unverified
    domain, invalid address...) fail immediately - retrying cannot fix them.
"""
import base64
import logging
import time
import uuid

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_URL = 'https://api.resend.com/emails'
MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 2.0


class EmailDeliveryError(Exception):
    """The email could not be delivered; the message says why (safe to log, contains no secrets)."""


def build_payload(message, default_from):
    """Turns a Django EmailMessage into Resend's JSON body. Pure function - easy to test."""
    payload = {
        'from': message.from_email or default_from,
        'to': list(message.to),
        'subject': message.subject,
    }
    if message.cc:
        payload['cc'] = list(message.cc)
    if message.bcc:
        payload['bcc'] = list(message.bcc)
    if getattr(message, 'reply_to', None):
        payload['reply_to'] = list(message.reply_to)

    html = None
    for alternative in getattr(message, 'alternatives', None) or []:
        content, mimetype = alternative[0], alternative[1]
        if mimetype == 'text/html':
            html = content
    if getattr(message, 'content_subtype', 'plain') == 'html':
        html = message.body                      # the whole body is HTML
    elif message.body:
        payload['text'] = message.body
    if html is not None:
        payload['html'] = html
    if 'html' not in payload and 'text' not in payload:
        payload['text'] = ' '                    # Resend requires a body; never send a truly empty email

    attachments = []
    for attachment in getattr(message, 'attachments', None) or []:
        if isinstance(attachment, (tuple, list)):
            filename, content = attachment[0], attachment[1]
            if isinstance(content, str):
                content = content.encode()
            attachments.append({'filename': filename, 'content': base64.b64encode(content).decode()})
        else:
            raise EmailDeliveryError('Unsupported attachment type for Resend (use (filename, content, mimetype) tuples).')
    if attachments:
        payload['attachments'] = attachments

    headers = dict(getattr(message, 'extra_headers', None) or {})
    if headers:
        payload['headers'] = headers
    return payload


def _error_text(response):
    try:
        data = response.json()
        return f"{data.get('name', 'error')}: {data.get('message', '')}".strip()
    except ValueError:
        return (response.text or '')[:200]


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', 10)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            try:
                self._send_one(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _send_one(self, message):
        if not self.api_key:
            raise EmailDeliveryError('RESEND_API_KEY is not set.')
        if not message.recipients():
            return
        payload = build_payload(message, settings.DEFAULT_FROM_EMAIL)
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'Idempotency-Key': uuid.uuid4().hex,    # same key on every retry of THIS message
        }
        last = 'no response'
        for attempt in range(1, MAX_ATTEMPTS + 1):
            wait = 0.5 * attempt
            try:
                response = requests.post(RESEND_URL, json=payload, headers=headers, timeout=self.timeout)
            except requests.exceptions.RequestException as exc:
                last = f'could not reach Resend ({exc.__class__.__name__})'
            else:
                try:
                    accepted = response.status_code == 200 and bool(response.json().get('id'))
                except ValueError:
                    accepted = False
                if accepted:
                    return
                last = f'HTTP {response.status_code} {_error_text(response)}'
                if response.status_code not in (429, 500, 502, 503, 504):
                    break                            # 4xx: retrying cannot help
                try:
                    wait = min(float(response.headers.get('retry-after', wait)), MAX_WAIT_SECONDS)
                except ValueError:
                    pass
            if attempt < MAX_ATTEMPTS:
                time.sleep(wait)
        logger.error('Resend email failed: %s', last)
        raise EmailDeliveryError(f'Resend did not accept the email: {last}')
