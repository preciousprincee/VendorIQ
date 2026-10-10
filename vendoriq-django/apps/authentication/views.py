from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
import hmac
from django.contrib.auth import authenticate
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer, UpdateProfileSerializer, ChangePasswordSerializer
from .models import User, LoginEvent
from .authentication import PASSWORD_CLAIM, password_fingerprint
from .cookies import session_response, set_refresh_cookie, clear_refresh_cookie, has_csrf_header
from django.conf import settings
from vendoriq import analytics


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            analytics.capture(user, 'sign_up', {'method': 'email', 'has_referral': bool(request.data.get('referred_by_code'))})
            return session_response(user, status=status.HTTP_201_CREATED)
        first_error = next(iter(serializer.errors.values()))[0]
        return Response({'error': str(first_error)}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Checked BEFORE authenticate() - two reasons. First, no point
        # doing the password hash comparison at all once locked out.
        # Second, and more important: this deliberately does NOT call
        # LoginEvent.record() for a blocked attempt below, specifically so
        # retrying against a locked-out email doesn't keep pushing the
        # window's start time forward - only the ORIGINAL burst of
        # failures (before lockout kicked in) counts, so the lockout
        # correctly expires LOGIN_LOCKOUT_WINDOW_MINUTES after the last
        # real attempt, not "whenever the attacker stops retrying".
        if LoginEvent.is_locked_out(email):
            from django.conf import settings
            return Response(
                {'error': f'Too many failed login attempts. Try again in {settings.LOGIN_LOCKOUT_WINDOW_MINUTES} minutes.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Emails are matched case-insensitively (the DB column is not), so
        # "Bob@Gmail.com" at login finds the account registered as
        # "bob@gmail.com". authenticate() needs the exact stored spelling.
        matched_user = User.objects.filter(email__iexact=email).first()
        user = authenticate(
            email=matched_user.email if matched_user else email,
            password=serializer.validated_data['password'],
        )

        if not user:
            # Attach to the real account if the email matches one (wrong
            # password case) so a pattern of failures shows up in that
            # user's login history - otherwise (unknown email) there's no
            # user to attach to, but the attempt is still logged by email.
            LoginEvent.record(request, email_attempted=email, user=matched_user, success=False)
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        LoginEvent.record(request, email_attempted=email, user=user, success=True)
        return session_response(user)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.stores.serializers import StoreSerializer
        from apps.stores.models import Store
        stores = Store.objects.filter(owner=request.user)
        user_data = UserSerializer(request.user).data
        user_data['stores'] = StoreSerializer(stores, many=True).data
        return Response({'user': user_data})

    def patch(self, request):
        """Edit-profile: name/phone only - see UpdateProfileSerializer for why email isn't editable here."""
        serializer = UpdateProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        from apps.stores.serializers import StoreSerializer
        from apps.stores.models import Store
        stores = Store.objects.filter(owner=request.user)
        user_data = UserSerializer(request.user).data
        user_data['stores'] = StoreSerializer(stores, many=True).data
        return Response({'user': user_data})


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ {current_password, new_password}."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.has_usable_password():
            return Response(
                {'error': 'Your account signs in with Google, so there is no password to change.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        # Every token issued before this moment is now invalid (see
        # authentication.py) - hand this session a fresh one.
        return session_response(request.user, extra={'ok': True})


class RefreshTokenView(APIView):
    """
    POST /api/auth/token/refresh/  ->  {token}

    Trades the refresh token for a new short-lived access token. The refresh token
    normally arrives in the HttpOnly cookie. Unlike SimpleJWT's stock view this also
    checks the account is still active and that the token was issued under the user's
    CURRENT password - so changing your password kills every session, not just access tokens.

    Migration: sessions created before cookies existed still hold their refresh token in
    localStorage. While AUTH_ALLOW_BODY_REFRESH is on, the app sends it once in the body;
    a valid one is moved into the HttpOnly cookie and the app then deletes its copy.
    Turn the setting off once old sessions have aged out (30 days).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        def fail():
            return clear_refresh_cookie(Response({'error': 'Your session has expired. Please sign in again.'}, status=status.HTTP_401_UNAUTHORIZED))

        cookie_value = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
        body = request.data if isinstance(request.data, dict) else {}
        body_value = body.get('refresh') if settings.AUTH_ALLOW_BODY_REFRESH else None
        raw = cookie_value or body_value
        if not isinstance(raw, str) or not raw:
            return fail()
        if cookie_value and not has_csrf_header(request):
            return Response({'error': 'Missing request header.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            refresh = RefreshToken(raw)
        except TokenError:
            return fail()
        user = User.objects.filter(pk=refresh.get('user_id'), is_active=True).first()
        claim = refresh.get(PASSWORD_CLAIM)
        # A refresh token with no password claim predates that check - make
        # its holder sign in again rather than carry an unrevocable session.
        if user is None or claim is None or not hmac.compare_digest(str(claim), password_fingerprint(user)):
            return fail()

        response = Response({'token': str(refresh.access_token)})
        if not cookie_value:
            set_refresh_cookie(response, raw)   # legacy localStorage session -> HttpOnly cookie
        return response


class LogoutView(APIView):
    """
    POST /api/auth/logout/ - clears the refresh cookie. A page script cannot delete an
    HttpOnly cookie, so signing out has to be a server call. (The cookie only exists
    for this browser; "sign out everywhere" is a password change, which revokes every token.)
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if request.COOKIES.get(settings.AUTH_COOKIE_NAME) and not has_csrf_header(request):
            return Response({'error': 'Missing request header.'}, status=status.HTTP_403_FORBIDDEN)
        return clear_refresh_cookie(Response({'ok': True}))
