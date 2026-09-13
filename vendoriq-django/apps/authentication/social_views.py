from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.response import Response

from .serializers import UserSerializer
from .views import get_tokens
from .models import LoginEvent


class GoogleLoginView(SocialLoginView):
    """
    POST here with {"id_token": "..."} - the ID token from Google's client-side
    Sign In With Google widget (the `credential` field in its onSuccess
    callback). dj-rest-auth/allauth handle verifying that token with Google
    and finding-or-creating the matching User; this view then throws away
    dj-rest-auth's own response format and returns our existing
    {token, refresh, user} shape instead, so the frontend's login handler
    doesn't need a second code path for "logged in via Google" vs "logged in
    via email/password" - it's the exact same response either way.
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client

    def get_response(self):
        LoginEvent.record(self.request, email_attempted=self.user.email, user=self.user, success=True)
        tokens = get_tokens(self.user)
        return Response({
            'user': UserSerializer(self.user).data,
            **tokens,
        })
