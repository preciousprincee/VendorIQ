from rest_framework import serializers
from .models import Store, Staff
from apps.authentication.models import User


class StoreSerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()
    sales_count = serializers.SerializerMethodField()
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = ['id', 'name', 'location', 'created_at', 'products_count', 'sales_count', 'staff_count']
        read_only_fields = ['id', 'created_at']

    def get_products_count(self, obj):
        return obj.products.count()

    def get_sales_count(self, obj):
        return obj.sales.count()

    def get_staff_count(self, obj):
        return obj.staff.count()


class StaffUserSerializer(serializers.ModelSerializer):
    """
    The ONLY user details a store sees about a staff member: name + the email the owner typed in.

    Never the full UserSerializer: staff are added by email, and any registered address can be added, so
    returning phone / referral code (which IS the phone number) / verification flags would let anybody
    look up another person's phone number just by "adding" them as staff.
    """
    class Meta:
        model = User
        fields = ['id', 'name', 'email']
        read_only_fields = fields


class StaffSerializer(serializers.ModelSerializer):
    user = StaffUserSerializer(read_only=True)

    class Meta:
        model = Staff
        fields = ['id', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']
