"""
The refresh token lives in an HttpOnly cookie, never in anything JavaScript can read.

Why: before this, the long-lived refresh token sat in localStorage, so any script that
ever ran on the page (a compromised dependency, an XSS bug) could copy it and use the
account from anywhere for 30 days. An HttpOnly cookie cannot be read by scripts at all.

How the pieces fit:
  * Sign-in / register / Google / change-password set the cookie and return only a
    SHORT-lived access token in the JSON body (the browser keeps that in memory).
  * POST /api/auth/token/refresh/ reads the cookie and returns a fresh access token.
  * POST /api/auth/logout/ clears the cookie (a script cannot delete an HttpOnly cookie).
  * The cookie is scoped to /api/auth/ so it is not sent with ordinary API calls.

Offline selling is unaffected: the offline till never needs a credential, only the
device's own storage. The cookie is used when the app is back online and has to sync.
"""
from django.conf import settings
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .authentication import PASSWORD_CLAIM, password_fingerprint
from .serializers import UserSerializer

CSRF_HEADER = 'X-Requested-With'
CSRF_VALUE = 'XMLHttpRequest'


def new_refresh_token(user):
    refresh = RefreshToken.for_user(user)
    # Bind the token to the current password (see authentication.py) - the access
    # token copies this claim from the refresh token.
    refresh[PASSWORD_CLAIM] = password_fingerprint(user)
    return refresh


def set_refresh_cookie(response, refresh_value):
    response.set_cookie(
        settings.AUTH_COOKIE_NAME,
        refresh_value,
        max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
        path=settings.AUTH_COOKIE_PATH,
        domain=settings.AUTH_COOKIE_DOMAIN,
        secure=settings.AUTH_COOKIE_SECURE,
        httponly=True,                       # the whole point: not readable by scripts
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    return response


def clear_refresh_cookie(response):
    response.delete_cookie(
        settings.AUTH_COOKIE_NAME,
        path=settings.AUTH_COOKIE_PATH,
        domain=settings.AUTH_COOKIE_DOMAIN,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    return response


def session_response(user, *, status=200, extra=None):
    """
    The response to every successful sign-in: the user and a short-lived access token in
    the body, the refresh token in the HttpOnly cookie. The refresh token is deliberately
    NOT in the body - anything in the body is readable by page scripts.
    """
    refresh = new_refresh_token(user)
    body = {'user': UserSerializer(user).data, 'token': str(refresh.access_token), **(extra or {})}
    return set_refresh_cookie(Response(body, status=status), str(refresh))


def has_csrf_header(request):
    """
    Cookie-authenticated endpoints (refresh, logout) must carry this header. A browser
    will not let a foreign site add a custom header without a CORS preflight that we
    refuse - so a page on another origin cannot trigger these calls with the victim's
    cookie. (SameSite already blocks the cookie cross-site; this is the second lock.)
    """
    return request.headers.get(CSRF_HEADER) == CSRF_VALUE
