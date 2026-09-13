from rest_framework import serializers
from .models import Sale, SaleItem
from apps.products.serializers import ProductSerializer


class SaleItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = ['id', 'product', 'quantity', 'unit_price', 'unit_cost', 'profit']

    def get_product(self, obj):
        return {'id': str(obj.product.id), 'name': obj.product.name}


class SaleSerializer(serializers.ModelSerializer):
    sale_items = SaleItemSerializer(many=True, read_only=True)
    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = ['id', 'total_amount', 'total_profit', 'sale_items', 'recorded_by_name', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.name if obj.recorded_by else None


class SaleItemInputSerializer(serializers.Serializer):
    """
    What one line item of an incoming "record a sale" request must look
    like. This used to be a bare serializers.DictField() - meaning
    literally nothing about productId or quantity was validated before
    reaching the view. In particular, a missing quantity silently defaulted
    to 0 and a NEGATIVE quantity sailed straight through: the stock check
    (`product.quantity < quantity`) trivially passes for a negative value,
    so the "sale" would actually INCREASE stock, and a negative
    unit_price * quantity would produce a negative total_amount/
    total_profit that then flows straight into the store's revenue/profit
    aggregates - completely silently. min_value=1 here closes that off at
    the validation layer, before any of that arithmetic ever runs.
    """
    productId = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class RecordSaleSerializer(serializers.Serializer):
    items = SaleItemInputSerializer(many=True, allow_empty=False)
