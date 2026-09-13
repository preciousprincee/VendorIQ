from rest_framework import serializers
from .models import Invoice, InvoiceItem


class InvoiceItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceItem
        fields = ['id', 'product', 'quantity', 'unit_price']

    def get_product(self, obj):
        return {'id': str(obj.product.id), 'name': obj.product.name}


class InvoiceSerializer(serializers.ModelSerializer):
    invoice_items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'customer_name', 'customer_email', 'customer_phone',
            'total_amount', 'status', 'invoice_items', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']
