from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from .models import User, LoginEvent


def get_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        'token': str(refresh.access_token),
        'refresh': str(refresh),
    }


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            tokens = get_tokens(user)
            return Response({
                'user': UserSerializer(user).data,
                **tokens
            }, status=status.HTTP_201_CREATED)
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

        user = authenticate(email=email, password=serializer.validated_data['password'])

        if not user:
            # Attach to the real account if the email matches one (wrong
            # password case) so a pattern of failures shows up in that
            # user's login history - otherwise (unknown email) there's no
            # user to attach to, but the attempt is still logged by email.
            matched_user = User.objects.filter(email__iexact=email).first()
            LoginEvent.record(request, email_attempted=email, user=matched_user, success=False)
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        LoginEvent.record(request, email_attempted=email, user=user, success=True)
        tokens = get_tokens(user)
        return Response({
            'user': UserSerializer(user).data,
            **tokens
        })


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.stores.serializers import StoreSerializer
        from apps.stores.models import Store
        stores = Store.objects.filter(owner=request.user)
        user_data = UserSerializer(request.user).data
        user_data['stores'] = StoreSerializer(stores, many=True).data
        return Response({'user': user_data})
