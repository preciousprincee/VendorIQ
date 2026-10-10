from datetime import timedelta
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from .serializers import UserSerializer
from .cookies import session_response
from .models import LoginEvent
from vendoriq import analytics


NEW_ACCOUNT_WINDOW_SECONDS = 20


def _first_signup_event(user):
    """
    True only for the first call per account. A double-click sends two parallel Google sign-in requests; both
    can see a brand-new account, but the sign-up must be counted once. cache.add is atomic (Redis SETNX).
    If the cache is unreachable we would rather count it once too many than lose it.
    """
    try:
        return bool(cache.add(f'analytics:signup:{user.pk}', 1, 3600))
    except Exception:
        return True


class GoogleLoginView(SocialLoginView):
    """
    POST here with {"id_token": "...", "referral_code": "..." (optional)} -
    the ID token from Google's client-side Sign In With Google widget (the
    `credential` field in its onSuccess callback). dj-rest-auth/allauth
    handle verifying that token with Google and finding-or-creating the
    matching User; this view then throws away dj-rest-auth's own response
    format and returns our existing {token, refresh, user} shape instead,
    so the frontend's login handler doesn't need a second code path for
    "logged in via Google" vs "logged in via email/password" - it's the
    exact same response either way.

    Same view handles both first-time Google signup and every later Google
    login (allauth finds-or-creates), so referral_code below is only ever
    applied to an account created in roughly this same request - see the
    comment in get_response.
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client

    def get_response(self):
        if not self.user.is_active:
            # allauth/dj-rest-auth don't reject a deactivated account here,
            # and this view would otherwise mint a token for it. (The JWT
            # would be refused on use, but a deactivated user should be told
            # so at sign-in, not get a token that mysteriously 401s.)
            return Response({'error': 'This account has been deactivated.'}, status=status.HTTP_403_FORBIDDEN)
        if not self.user.email_verified:
            # Signing in with Google proves control of this address.
            self.user.email_verified = True
            self.user.save(update_fields=['email_verified'])
            analytics.capture(self.user, 'email_verified', {'method': 'google'})
        LoginEvent.record(self.request, email_attempted=self.user.email, user=self.user, success=True)

        # True only when this very request created the account (first Google sign-in). The frontend uses it
        # to tell "signed up" from "logged in" for product analytics. The window is seconds, not minutes,
        # because a genuine sign-up row is written moments before this line runs.
        is_new_account = self.user.created_at >= timezone.now() - timedelta(seconds=NEW_ACCOUNT_WINDOW_SECONDS)

        if is_new_account and _first_signup_event(self.user):
            analytics.capture(self.user, 'sign_up', {'method': 'google', 'has_referral': bool(self.request.data.get('referred_by_code'))})

        referral_code = self.request.data.get('referred_by_code', '')
        if referral_code and self.user.created_at >= timezone.now() - timedelta(minutes=5):
            # Guards against a stale ?ref= sitting around in someone's
            # browser attributing a REFERRAL to a routine login on an
            # account that's been around for months - Referral.referred_user
            # is a OneToOneField either way, so record_referral_if_applicable
            # is also naturally a no-op for an account that already has one.
            from apps.referrals.services import record_referral_if_applicable
            record_referral_if_applicable(self.user, referral_code)

        return session_response(self.user, extra={'isNewAccount': is_new_account})
