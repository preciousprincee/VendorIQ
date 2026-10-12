from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView

from vendoriq import analytics
from vendoriq.throttles import VerificationSendThrottle, VerificationConfirmThrottle
from .models import VerificationCode
from .phone import normalize_phone
from .serializers import UserSerializer, UpdateProfileSerializer, PHONE_ERROR, phone_in_use
from .verification import (
    VerificationError, check_code, claim_phone, send_email_code, send_phone_code,
    RESEND_COOLDOWN_SECONDS,
)


def _error(exc):
    body = {'error': exc.message}
    if exc.retry_after:
        body['retryAfter'] = exc.retry_after
    return Response(body, status=exc.status_code)


def _user_payload(user):
    return {'user': UserSerializer(user).data}


class SendEmailCodeView(APIView):
    """POST /api/auth/verify/email/send/ - emails a 6-digit code to the account's address."""
    permission_classes = [IsAuthenticated]
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, VerificationSendThrottle]

    def post(self, request):
        user = request.user
        if user.email_verified:
            return Response({'ok': True, 'alreadyVerified': True, **_user_payload(user)})
        try:
            send_email_code(user)
        except VerificationError as exc:
            return _error(exc)
        # The code is NEVER returned to the browser - it only ever travels by email.
        return Response({'ok': True, 'cooldown': RESEND_COOLDOWN_SECONDS})


class ConfirmEmailCodeView(APIView):
    """POST /api/auth/verify/email/confirm/ {code}"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, VerificationConfirmThrottle]

    def post(self, request):
        user = request.user
        if not user.email_verified:
            try:
                check_code(user, VerificationCode.Channel.EMAIL, user.email, request.data.get('code'))
            except VerificationError as exc:
                return _error(exc)
            user.email_verified = True
            user.save(update_fields=['email_verified'])
            analytics.capture(user, 'email_verified', {'method': 'code'})
        return Response({'ok': True, **_user_payload(user)})


class SendPhoneCodeView(APIView):
    """
    POST /api/auth/verify/phone/send/ {phone?} - texts a code. If `phone` is
    given (first-time entry for Google sign-ups, or correcting a typo) it
    replaces the unverified number on the account first.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, VerificationSendThrottle]

    def post(self, request):
        user = request.user
        if user.phone_verified:
            return Response({'ok': True, 'alreadyVerified': True, **_user_payload(user)})

        raw = request.data.get('phone')
        if raw not in (None, ''):
            canonical = normalize_phone(raw)
            if not canonical:
                return Response({'error': PHONE_ERROR}, status=status.HTTP_400_BAD_REQUEST)
            if canonical != normalize_phone(user.phone):
                if phone_in_use(canonical, exclude_pk=user.pk):
                    return Response({'error': 'This phone number is already used by another account.'}, status=status.HTTP_400_BAD_REQUEST)
                try:
                    claim_phone(user, canonical)
                except VerificationError as exc:
                    return _error(exc)

        if not normalize_phone(user.phone):
            return Response({'error': 'Enter your phone number first.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            send_phone_code(user)
        except VerificationError as exc:
            return _error(exc)
        # The code is NEVER returned to the browser - it only ever travels by SMS.
        return Response({'ok': True, 'cooldown': RESEND_COOLDOWN_SECONDS, **_user_payload(user)})


class ConfirmPhoneCodeView(APIView):
    """POST /api/auth/verify/phone/confirm/ {code}"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [*api_settings.DEFAULT_THROTTLE_CLASSES, VerificationConfirmThrottle]

    def post(self, request):
        user = request.user
        if not user.phone_verified:
            phone = normalize_phone(user.phone)
            if not phone:
                return Response({'error': 'Enter your phone number first.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                check_code(user, VerificationCode.Channel.PHONE, phone, request.data.get('code'))
            except VerificationError as exc:
                return _error(exc)
            # Two accounts can each hold the same UNVERIFIED number; whoever
            # proves it first wins. Re-check right before committing.
            if phone_in_use(phone, exclude_pk=user.pk):
                return Response({'error': 'This phone number was just verified by another account.'}, status=status.HTTP_400_BAD_REQUEST)
            user.phone_verified = True
            user.save(update_fields=['phone_verified'])
            analytics.capture(user, 'phone_verified', {'method': 'code'})
        return Response({'ok': True, **_user_payload(user)})
