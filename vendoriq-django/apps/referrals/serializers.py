from django.core.validators import RegexValidator
from rest_framework import serializers
from .models import PayoutAccount, Referral, ReferralCommission


class CommissionSerializer(serializers.ModelSerializer):
    referredUserName = serializers.CharField(source='referral.referred_user.name')
    amountNgn = serializers.DecimalField(source='amount_ngn', max_digits=10, decimal_places=2)
    failureReason = serializers.CharField(source='failure_reason')
    paidAt = serializers.DateTimeField(source='paid_at')
    createdAt = serializers.DateTimeField(source='created_at')

    class Meta:
        model = ReferralCommission
        fields = ['id', 'referredUserName', 'amountNgn', 'status', 'failureReason', 'paidAt', 'createdAt']


class PayoutAccountSerializer(serializers.ModelSerializer):
    bankName = serializers.CharField(source='bank_name', read_only=True)
    accountNumber = serializers.CharField(source='account_number', read_only=True)
    accountName = serializers.CharField(source='account_name', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = PayoutAccount
        fields = ['bankName', 'accountNumber', 'accountName', 'updatedAt']


class SetPayoutAccountSerializer(serializers.Serializer):
    # Both get interpolated straight into a Paystack API URL
    # (paystack.py::resolve_account) - constraining the shape here isn't
    # just cosmetic validation, it's what stops arbitrary characters from
    # ever reaching that query string. Paystack's own bank codes are plain
    # digit strings (e.g. "058", "011").
    bank_code = serializers.CharField(validators=[RegexValidator(r'^\d+$', 'Enter a valid bank code.')])
    account_number = serializers.CharField(validators=[RegexValidator(r'^\d{10}$', 'Account number must be exactly 10 digits.')])
