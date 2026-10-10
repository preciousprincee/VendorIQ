"""Tighter, per-user throttles for endpoints that cost money or can be abused to hit third parties. Rates live in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] (settings.py)."""
from rest_framework.throttling import UserRateThrottle


class AIChatThrottle(UserRateThrottle):
    # Every call is a paid LLM request; the global 300/min is far too loose.
    scope = 'ai_chat'


class InvoiceSendThrottle(UserRateThrottle):
    # Sends a real email to an address typed by the caller - without a tight
    # cap any account (Pro trial included) could use it to spam strangers
    # from VendorIQ's sender domain.
    scope = 'invoice_send'


class VerificationSendThrottle(UserRateThrottle):
    # Belt-and-braces on top of the per-user/per-number caps in
    # apps/authentication/verification.py: requesting codes sends real
    # emails/SMS, so the request rate itself is limited too.
    scope = 'verify_send'


class VerificationConfirmThrottle(UserRateThrottle):
    scope = 'verify_confirm'


class StaffAddThrottle(UserRateThrottle):
    # "Add staff by email" answers differently for registered vs unregistered
    # addresses, so unbounded use would let someone probe which emails have
    # accounts. A real store adds a handful of staff, not dozens per hour.
    scope = 'staff_add'


class BackupThrottle(UserRateThrottle):
    # A full backup walks every table for the store - cheap for one request,
    # expensive if hammered.
    scope = 'backup'
