from rest_framework.exceptions import APIException
from rest_framework import status


class UpgradeRequired(APIException):
    """
    Raised anywhere a Free-plan user hits a Pro-only feature or a plan
    limit. Uses HTTP 402 Payment Required - distinct from a plain 403, so
    the frontend can tell "you're not allowed" (403, e.g. wrong staff role)
    apart from "you're allowed, but need to upgrade" (402) and route the
    second one to the upgrade UI instead of a generic access-denied toast.

    vendoriq/utils.py's custom_exception_handler special-cases this class to
    preserve `code`/`feature`/`title`/`cta` in the JSON body instead of
    flattening it to a bare {"error": "..."} string - see that file.
    """
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = 'upgrade_required'

    def __init__(self, message, *, code='UPGRADE_REQUIRED', feature=None, title='Upgrade to Pro', limit=None, current=None):
        super().__init__(detail=message, code=code)
        self.extra_data = {
            'error': str(message),
            'code': code,  # 'UPGRADE_REQUIRED' (feature gate) or 'LIMIT_REACHED' (usage cap)
            'feature': feature,  # matches a key in apps.billing.plans.FEATURES, or None for a plain limit
            'title': title,
            'upgradeRequired': True,
        }
        if limit is not None:
            self.extra_data['limit'] = limit
        if current is not None:
            self.extra_data['current'] = current
