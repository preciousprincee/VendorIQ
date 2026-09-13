from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        # Upgrade/limit-gate errors (apps.billing.exceptions.UpgradeRequired)
        # carry structured fields (code, feature, title, upgradeRequired,
        # limit/current) the frontend's upgrade modal needs - preserve them
        # instead of flattening to a bare {"error": "..."} string below.
        extra_data = getattr(exc, 'extra_data', None)
        if extra_data is not None:
            response.data = extra_data
            return response

        # Flatten error messages
        errors = response.data
        if isinstance(errors, dict):
            first_key = next(iter(errors))
            first_error = errors[first_key]
            if isinstance(first_error, list):
                message = first_error[0]
            else:
                message = str(first_error)
            response.data = {'error': message}
        elif isinstance(errors, list):
            response.data = {'error': errors[0]}

    return response
