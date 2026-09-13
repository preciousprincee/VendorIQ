from rest_framework import serializers
from .models import Store, Staff
from apps.authentication.serializers import UserSerializer


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


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Staff
        fields = ['id', 'user', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']
