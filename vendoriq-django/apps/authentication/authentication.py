"""
JWT authentication that ties every token to the password it was issued under.

Why: SimpleJWT has no server-side session, so before this a stolen token kept
working for its whole 7-day lifetime EVEN AFTER the owner changed their
password (the one thing people do when they think they've been compromised).
Each token now carries a short fingerprint of the user's current password
hash; changing the password changes the fingerprint, so every older token is
rejected on its next use (the frontend already logs the user out on a 401).

Tokens issued before this class existed carry no fingerprint claim; those are
still accepted so deploying this doesn't log everybody out at once - they
simply age out within the normal token lifetime.
"""
import hashlib
import hmac

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

PASSWORD_CLAIM = 'pwd'


def password_fingerprint(user):
    digest = hmac.new(
        settings.SECRET_KEY.encode(), (user.password or '').encode(), hashlib.sha256,
    ).hexdigest()
    return digest[:20]


class PasswordVersionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        claim = validated_token.get(PASSWORD_CLAIM)
        if claim is not None and not hmac.compare_digest(str(claim), password_fingerprint(user)):
            raise AuthenticationFailed('Your session has expired. Please sign in again.', code='token_not_valid')
        return user
