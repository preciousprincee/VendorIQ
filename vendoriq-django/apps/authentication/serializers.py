from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from .models import User
from .verification import VerificationError, claim_phone
from .phone import normalize_phone

PHONE_ERROR = 'Enter a valid Nigerian phone number, e.g. 08012345678.'


def phone_in_use(canonical, exclude_pk=None):
    """
    A number is taken if another account holds it as phone OR as its referral
    code (which is the same number) AND has VERIFIED it. A number that is
    only sitting unverified on some other account can still be claimed by
    its real owner (see verification.claim_phone) - otherwise anyone could
    register with a stranger's number and lock them out of it for good.
    """
    qs = User.objects.filter(Q(phone=canonical) | Q(referral_code=canonical), phone_verified=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def check_new_password(value):
    """Shared by registration and change-password so the two can never enforce different rules."""
    if not any(c.isupper() for c in value):
        raise serializers.ValidationError('Password must contain at least one uppercase letter.')
    if not any(c.isdigit() for c in value):
        raise serializers.ValidationError('Password must contain at least one number.')
    try:
        validate_password(value)
    except DjangoValidationError as e:
        raise serializers.ValidationError(e.messages[0])
    return value


class RegisterSerializer(serializers.ModelSerializer):
    # Declared explicitly (rather than inherited from the model field) so DRF
    # does NOT attach its case-SENSITIVE UniqueValidator - the model's
    # `unique=True` on email is case-sensitive on Postgres, which would let
    # "Bob@x.com" and "bob@x.com" both register (two accounts for one person
    # - a free second trial, split data). validate_email below does the
    # uniqueness check case-insensitively instead.
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, min_length=8)
    # Optional - who referred this signup, if anyone. Deliberately NOT
    # named referral_code: that name is already the User model's own
    # OUTGOING code (the one THIS user shares to refer others - see
    # apps/authentication/models.py). This is the opposite direction - an
    # INCOMING code someone else gave them - so it gets its own name to
    # avoid two different meanings sharing one field name. Popped out in
    # create() below and handed to
    # apps.referrals.services.record_referral_if_applicable, which quietly
    # ignores anything blank, unknown, or self-referential rather than
    # failing registration over it.
    referred_by_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # REQUIRED: the phone number is the free-trial anti-abuse key and the
    # referral code, and is verified by SMS right after signup.
    phone = serializers.CharField(max_length=20, required=True, allow_blank=False, error_messages={
        'required': 'Phone number is required.', 'blank': 'Phone number is required.',
    })

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'password', 'referred_by_code']
        read_only_fields = ['id']

    def validate_email(self, value):
        email = User.objects.normalize_email((value or '').strip()).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return email

    def validate_password(self, value):
        # AUTH_PASSWORD_VALIDATORS (settings.py) run inside check_new_password.
        return check_new_password(value)

    def validate_phone(self, value):
        """Required, must be a real Nigerian number, and must not belong to an account that has already verified it."""
        canonical = normalize_phone((value or '').strip())
        if not canonical:
            raise serializers.ValidationError(PHONE_ERROR)
        if phone_in_use(canonical):
            raise serializers.ValidationError('An account with this phone number already exists.')
        return canonical

    def create(self, validated_data):
        referred_by_code = validated_data.pop('referred_by_code', '')
        phone = validated_data.pop('phone')
        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            try:
                claim_phone(user, phone)  # takes the number from any unverified squatter
            except VerificationError as exc:
                raise serializers.ValidationError({'phone': [exc.message]})
        from apps.referrals.services import record_referral_if_applicable
        record_referral_if_applicable(user, referred_by_code)
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    # Lets the Settings page know whether "change password" applies (a
    # Google-only account has no usable password to change).
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'name', 'email', 'phone', 'phone_verified', 'email_verified', 'needs_verification',
            'referral_code', 'has_password', 'created_at',
        ]
        read_only_fields = ['id', 'phone_verified', 'email_verified', 'referral_code', 'has_password', 'created_at']

    # True until BOTH email and phone are verified - the frontend shows the
    # verification screen while this is set.
    needs_verification = serializers.SerializerMethodField()

    def get_needs_verification(self, obj):
        return not obj.is_fully_verified

    def get_has_password(self, obj):
        return obj.has_usable_password()


class UpdateProfileSerializer(serializers.ModelSerializer):
    """
    Backs PATCH /api/auth/me/ (Settings > Account). Deliberately only
    name/phone - NOT email, which doubles as the login identifier
    (USERNAME_FIELD) and would need its own re-verification flow to change
    safely.

    The phone number is also the user's referral code, so:
      - it cannot be changed once phone_verified is True,
      - it must be a valid number, and
      - it must not already belong to another account (which would hand
        them someone else's referral code).
    Sending the phone number they already have is always fine (no-op).
    """
    name = serializers.CharField(max_length=255, min_length=1)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['name', 'phone']

    def validate_phone(self, value):
        user = self.instance
        value = (value or '').strip()
        new = normalize_phone(value) if value else ''
        # Required - a phone number can be CHANGED here but never removed.
        if not new:
            raise serializers.ValidationError(PHONE_ERROR if value else 'Phone number is required.')
        if new == normalize_phone(user.phone):
            return user.phone or ''  # unchanged
        if user.phone_verified:
            raise serializers.ValidationError(
                'Your phone number has been verified and can no longer be changed here. Contact support if you need to change it.'
            )
        if phone_in_use(new, exclude_pk=user.pk):
            raise serializers.ValidationError('This phone number is already used by another account.')
        return new

    def update(self, instance, validated_data):
        new_phone = validated_data.pop('phone', None)
        with transaction.atomic():
            if 'name' in validated_data:
                instance.name = validated_data['name']
                instance.save(update_fields=['name'])
            if new_phone and new_phone != normalize_phone(instance.phone):
                try:
                    claim_phone(instance, new_phone)
                except VerificationError as exc:
                    raise serializers.ValidationError({'phone': [exc.message]})
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        if not self.context['request'].user.check_password(value):
            raise serializers.ValidationError('Your current password is incorrect.')
        return value

    def validate_new_password(self, value):
        return check_new_password(value)
