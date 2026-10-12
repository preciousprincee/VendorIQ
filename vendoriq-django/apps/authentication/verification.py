"""
Email + phone ownership verification (6-digit one-time codes).

Why both exist: the phone number is the anti-abuse key for the free trial and
the user's referral code, and the email is the login identifier and where
invoices/receipts/notices go. Neither means anything until the person proves
they control it. Until both are verified an account can browse the app but
cannot start a trial or pay (see require_verified below).

Safety properties (each one closes a specific abuse):
  * only a keyed HASH of the code is stored           -> a DB leak yields no live codes
  * codes expire after 10 minutes and are single-use  -> a stolen/old code is worthless
  * 5 wrong guesses lock the code                     -> a 6-digit code can't be brute-forced
  * a resend cooldown + hourly cap per user           -> can't be used to spam an inbox / burn SMS credit
  * a daily cap per PHONE NUMBER across all accounts  -> can't be used to SMS-bomb somebody else's number
  * a code is bound to the exact address/number it was sent to
"""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from . import sms
from .models import User, VerificationCode

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
RESEND_COOLDOWN_SECONDS = 60
MAX_SENDS_PER_HOUR = 5
MAX_ATTEMPTS = 5
MAX_SMS_PER_NUMBER_PER_DAY = 6


class VerificationError(Exception):
    """A problem the person can act on - the message is shown to them as-is."""
    def __init__(self, message, status_code=400, retry_after=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


def require_verified(user):
    """Gate for actions that must not be available to unverified accounts (free trial, paid checkout)."""
    if user.is_fully_verified:
        return
    missing = []
    if not user.email_verified:
        missing.append('email address')
    if not user.phone_verified:
        missing.append('phone number')
    message = f"Please verify your {' and '.join(missing)} first."
    exc = PermissionDenied(message)
    # vendoriq.utils.custom_exception_handler returns extra_data verbatim, so
    # the frontend gets the machine-readable `code` (it would otherwise be
    # flattened away to just the message).
    exc.extra_data = {'error': message, 'code': 'verification_required'}
    raise exc


def _hash_code(user_id, channel, target, code):
    message = f'{user_id}:{channel}:{target}:{code}'.encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def _generate_code():
    return f'{secrets.randbelow(10 ** 6):06d}'


def issue_code(user, channel, target):
    """Creates a fresh code for (user, channel, target), invalidating any earlier live one. Returns the plaintext code."""
    now = timezone.now()
    recent = VerificationCode.objects.filter(user=user, channel=channel)

    last = recent.order_by('-created_at').first()
    # The cooldown stops re-sending to the SAME target. Fixing a typo'd phone
    # number (a different target) must not make the person wait a minute; the
    # hourly cap below and the per-number daily cap still bound the abuse.
    if last is not None and last.target == target:
        wait = RESEND_COOLDOWN_SECONDS - int((now - last.created_at).total_seconds())
        if wait > 0:
            raise VerificationError(f'Please wait {wait} seconds before requesting another code.', 429, retry_after=wait)
    if recent.filter(created_at__gte=now - timedelta(hours=1)).count() >= MAX_SENDS_PER_HOUR:
        raise VerificationError('Too many codes requested. Please try again in an hour.', 429, retry_after=3600)
    if channel == VerificationCode.Channel.PHONE:
        sent_to_number = VerificationCode.objects.filter(
            channel=VerificationCode.Channel.PHONE, target=target, created_at__gte=now - timedelta(hours=24),
        ).count()
        if sent_to_number >= MAX_SMS_PER_NUMBER_PER_DAY:
            raise VerificationError('Too many codes have been sent to this number today. Please try again tomorrow.', 429)

    code = _generate_code()
    with transaction.atomic():
        recent.filter(consumed_at__isnull=True).update(consumed_at=now)
        row = VerificationCode.objects.create(
            user=user, channel=channel, target=target,
            code_hash=_hash_code(user.id, channel, target, code),
            expires_at=now + CODE_TTL,
        )
    return code, row


def check_code(user, channel, target, code):
    """Validates a submitted code; consumes it on success, raises VerificationError otherwise."""
    code = ''.join(ch for ch in str(code or '') if ch.isdigit())
    if len(code) != 6:
        raise VerificationError('Enter the 6-digit code.')

    now = timezone.now()
    outcome = None
    # The attempt counter must be COMMITTED even when the guess is wrong, so
    # decide the outcome inside the transaction and raise only after it.
    with transaction.atomic():
        row = (
            VerificationCode.objects.select_for_update()
            .filter(user=user, channel=channel, target=target, consumed_at__isnull=True, expires_at__gt=now)
            .order_by('-created_at').first()
        )
        if row is None:
            outcome = 'expired'
        elif row.attempts >= MAX_ATTEMPTS:
            outcome = 'locked'
        else:
            row.attempts += 1
            if hmac.compare_digest(row.code_hash, _hash_code(user.id, channel, target, code)):
                row.consumed_at = now
                outcome = 'ok'
            else:
                outcome = 'wrong'
            row.save(update_fields=['attempts', 'consumed_at'])

    if outcome == 'ok':
        return
    if outcome == 'expired':
        raise VerificationError('That code has expired or was never requested. Request a new one.')
    if outcome == 'locked':
        raise VerificationError('Too many incorrect attempts. Request a new code.')
    raise VerificationError('That code is incorrect.')


# --- delivery ---------------------------------------------------------------

def send_email_code(user):
    """Emails a code to user.email. Raises VerificationError if it could not be delivered."""
    code, row = issue_code(user, VerificationCode.Channel.EMAIL, user.email)
    text = (
        f'Hi {user.name},\n\nYour VendorIQ verification code is {code}.\n'
        f'It expires in 10 minutes. If you did not create a VendorIQ account, you can ignore this email.\n'
    )
    html = (
        f'<div style="font-family:Arial,sans-serif;max-width:420px;margin:auto">'
        f'<p>Hi {_escape(user.name)},</p><p>Your VendorIQ verification code is:</p>'
        f'<p style="font-size:30px;font-weight:700;letter-spacing:6px">{code}</p>'
        f'<p style="color:#666;font-size:13px">It expires in 10 minutes. If you did not create a VendorIQ account, '
        f'you can ignore this email.</p></div>'
    )
    try:
        message = EmailMultiAlternatives('Your VendorIQ verification code', text, to=[user.email])
        message.attach_alternative(html, 'text/html')
        message.send(fail_silently=False)
    except Exception:
        row.delete()  # nothing was delivered - don't make them wait out the cooldown
        logger.error('Verification email for user %s failed', user.pk, exc_info=True)
        raise VerificationError('We could not send the email right now. Please try again shortly.', 502)
    return code


def send_phone_code(user):
    """Texts a code to user.phone (canonical form). Raises VerificationError if it could not be delivered."""
    code, row = issue_code(user, VerificationCode.Channel.PHONE, user.phone)
    try:
        sms.send_sms(user.phone, f'Your VendorIQ verification code is {code}. It expires in 10 minutes.')
    except sms.SMSNotConfigured:
        row.delete()
        raise VerificationError('Phone verification is temporarily unavailable. Please contact support.', 503)
    except sms.SMSError as exc:
        row.delete()
        raise VerificationError(str(exc), 502)
    return code


def _escape(value):
    from django.utils.html import escape
    return escape(value)


# --- phone ownership ----------------------------------------------------------

def claim_phone(user, canonical):
    """
    Sets `canonical` as user's number.

    A number held by another account that has NOT verified it is taken from
    that account - otherwise anybody could register with someone else's
    number and permanently block the real owner from ever using it. A number
    held by a VERIFIED account is never taken.
    """
    with transaction.atomic():
        holders = list(
            User.objects.select_for_update()
            .filter(Q(phone=canonical) | Q(referral_code=canonical)).exclude(pk=user.pk)
        )
        if any(h.phone_verified for h in holders):
            raise VerificationError('This phone number is already used by another account.')
        for holder in holders:
            holder.phone = None
            holder.save(update_fields=['phone'])  # also clears its referral_code (see User.save)
        user.phone = canonical
        user.phone_verified = False
        user.save(update_fields=['phone', 'phone_verified'])
