from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'password']
        read_only_fields = ['id']

    def validate_password(self, value):
        if not any(c.isupper() for c in value):
            raise serializers.ValidationError('Password must contain at least one uppercase letter.')
        if not any(c.isdigit() for c in value):
            raise serializers.ValidationError('Password must contain at least one number.')
        # Also run Django's own validators (AUTH_PASSWORD_VALIDATORS in
        # settings.py - currently minimum length, common-password blocklist,
        # and not-entirely-numeric). This import used to sit here unused -
        # the checks above ran, but this exact call never did, so
        # AUTH_PASSWORD_VALIDATORS had zero actual effect on registration.
        # No `user=` passed since there's no User instance yet at
        # registration time - that only affects
        # UserAttributeSimilarityValidator (not configured above), every
        # other validator works fine against the raw password alone.
        try:
            validate_password(value)
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.messages[0])
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'created_at']
        read_only_fields = ['id', 'created_at']
