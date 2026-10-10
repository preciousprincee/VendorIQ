"""
One canonical phone-number format for the whole backend.

A user's phone number is now also their REFERRAL CODE (see
User.save() in models.py), so "the same number typed two different ways"
- +234 801 234 5678, 2348012345678, 08012345678, 8012345678 - must always
resolve to the same value everywhere a phone is compared: referral-code
lookup, duplicate-account checks, and the free-trial abuse check in
apps/billing/entitlements.py. Previously each place normalized (or didn't)
on its own, which is how '+234 801...' and '0801...' ended up not matching.

Canonical form is the 11-digit local Nigerian format, 0XXXXXXXXXX.
"""


def normalize_phone(raw):
    """Returns the canonical 0XXXXXXXXXX form, or '' if `raw` isn't a valid Nigerian mobile number."""
    digits = ''.join(ch for ch in str(raw or '') if ch.isdigit())
    if digits.startswith('00234') and len(digits) == 15:
        digits = '0' + digits[5:]
    elif digits.startswith('234') and len(digits) == 13:
        digits = '0' + digits[3:]
    elif len(digits) == 10 and not digits.startswith('0'):
        digits = '0' + digits
    if len(digits) != 11 or not digits.startswith('0'):
        return ''
    return digits
