import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

PAYSTACK_BASE_URL = 'https://api.paystack.co'


class PaystackError(Exception):
    """Raised for any non-2xx or status:false response - callers decide what to show the user."""
    def __init__(self, message, response_data=None):
        super().__init__(message)
        self.response_data = response_data


class PaystackAmbiguousError(PaystackError):
    """
    We could not tell whether Paystack acted on the request (timeout,
    connection reset, 5xx, unreadable body). For a money-moving POST this is
    NOT the same as "Paystack said no": the transfer may well have gone out.
    Callers must never blindly retry these - see referrals.services.attempt_payout.
    """


def _request(method, path, full=False, **kwargs):
    if not settings.PAYSTACK_SECRET_KEY:
        raise PaystackError('Payments are not configured (PAYSTACK_SECRET_KEY missing).')
    try:
        response = requests.request(
            method, f'{PAYSTACK_BASE_URL}{path}',
            headers={'Authorization': f'Bearer {settings.PAYSTACK_SECRET_KEY}', 'Content-Type': 'application/json'},
            timeout=15, **kwargs,
        )
    except requests.exceptions.RequestException as exc:
        logger.error('Paystack request failed: %s %s', method, path, exc_info=True)
        raise PaystackAmbiguousError('Could not reach Paystack. Please try again shortly.') from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code not in (200, 201) or not data.get('status'):
        logger.error('Paystack %s %s returned %s: %s', method, path, response.status_code, response.text[:500])
        # 5xx (or a body we couldn't parse): Paystack may have processed it.
        # A 4xx with a readable body is a definite refusal.
        error_cls = PaystackAmbiguousError if (response.status_code >= 500 or not data) else PaystackError
        raise error_cls(data.get('message') or 'Paystack request failed.', response_data=data)

    return data if full else data.get('data')


def list_banks():
    """
    GET /bank - every Nigerian bank/fintech with its code, for the payout-account dropdown.

    Paystack returns only 50 banks per request by default (Nigeria has several
    hundred incl. microfinance banks and fintechs), so the old single call
    silently showed a truncated list - "my bank isn't in the dropdown". This
    walks the cursor pages (100 at a time) until Paystack says there are no more.
    """
    banks, cursor = [], None
    for _ in range(10):  # hard stop: 1,000 banks is far beyond reality
        params = {'country': 'nigeria', 'currency': 'NGN', 'perPage': 100, 'use_cursor': 'true'}
        if cursor:
            params['next'] = cursor
        page = _request('GET', '/bank', full=True, params=params)
        for bank in page.get('data') or []:
            if bank.get('active') is False or bank.get('is_deleted'):
                continue
            if bank.get('name') and bank.get('code'):
                banks.append({'name': bank['name'], 'code': bank['code']})
        cursor = (page.get('meta') or {}).get('next')
        if not cursor:
            break
    # Same code can appear under two names on Paystack - keep the first of each (name, code).
    seen, unique = set(), []
    for bank in sorted(banks, key=lambda b: b['name'].lower()):
        key = (bank['name'], bank['code'])
        if key not in seen:
            seen.add(key)
            unique.append(bank)
    return unique


def resolve_account(account_number, bank_code):
    """
    GET /bank/resolve - confirms an account_number actually belongs to a
    real account at that bank and returns its registered name, so we NEVER
    save/pay out to an account based purely on what the user typed.
    """
    # params= so the values are URL-encoded - interpolating them into the path
    # let a crafted value smuggle extra query parameters into a request that
    # carries our secret key.
    return _request('GET', '/bank/resolve', params={'account_number': account_number, 'bank_code': bank_code})


def create_transfer_recipient(name, account_number, bank_code):
    """POST /transferrecipient - registers a payout destination, returns a recipient_code to transfer to later."""
    return _request('POST', '/transferrecipient', json={
        'type': 'nuban', 'name': name, 'account_number': account_number, 'bank_code': bank_code, 'currency': 'NGN',
    })


def initiate_transfer(recipient_code, amount_kobo, reason, reference):
    """
    POST /transfer - pays a referrer. Draws from VendorIQ's own Paystack
    balance (this is real money the business must actually hold, not
    something Paystack advances) and, on a live account with per-transfer
    OTP still enabled, returns status='otp' rather than completing - see
    the note in apps/referrals/services.py and CHANGES.md about disabling
    that with Paystack support for this to be truly automatic.
    """
    return _request('POST', '/transfer', json={
        'source': 'balance', 'amount': amount_kobo, 'recipient': recipient_code, 'reason': reason, 'reference': reference,
    })
