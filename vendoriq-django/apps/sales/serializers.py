from decimal import Decimal

from rest_framework import serializers

from .models import Sale, SaleItem, SalePayment, SaleReturn, Shift

METHOD_CHOICES = ['CASH', 'TRANSFER', 'CARD']
MONEY = dict(max_digits=12, decimal_places=2)


class SaleItemSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = ['id', 'product', 'quantity', 'returned_quantity', 'unit_price', 'unit_cost', 'profit']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Cost and profit are financial data reserved for owners/managers
        # (the list view already hid the TOTALS from cashiers, but the
        # per-line cost/profit leaked through here).
        if self.context.get('role') == 'CASHIER':
            data.pop('unit_cost', None)
            data.pop('profit', None)
        return data

    def get_product(self, obj):
        return {'id': str(obj.product.id), 'name': obj.product.name}


class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment
        fields = ['id', 'method', 'amount', 'created_at', 'is_debt_payment']

    is_debt_payment = serializers.SerializerMethodField()

    def get_is_debt_payment(self, obj):
        return obj.customer_payment_id is not None


class SaleReturnSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleReturn
        fields = ['id', 'return_value', 'refund_amount', 'refund_method', 'restocked', 'reason', 'created_at']


class SaleSerializer(serializers.ModelSerializer):
    sale_items = SaleItemSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    returns = SaleReturnSerializer(many=True, read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    receipt_no = serializers.CharField(read_only=True)
    balance_due = serializers.DecimalField(read_only=True, **MONEY)
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = Sale
        fields = [
            'id', 'receipt_no', 'client_id', 'total_amount', 'total_profit', 'subtotal', 'discount_amount',
            'returned_amount', 'amount_paid', 'amount_refunded', 'credit_amount', 'balance_due', 'payment_status',
            'cash_tendered', 'change_given', 'note', 'customer', 'sale_items', 'payments', 'returns',
            'recorded_by_name', 'needs_review', 'review_notes', 'synced_at', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.context.get('role') == 'CASHIER':
            data.pop('total_profit', None)
            data.pop('review_notes', None)  # owner-facing audit detail
        return data

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.name if obj.recorded_by else None

    def get_customer(self, obj):
        return {'id': str(obj.customer_id), 'name': obj.customer.name} if obj.customer_id else None


# --- input -----------------------------------------------------------------

class SaleItemInputSerializer(serializers.Serializer):
    """
    What one line item of an incoming "record a sale" request must look
    like. min_value=1 closes off the old hole where a negative quantity
    INCREASED stock and produced a negative revenue/profit that flowed
    straight into the store's aggregates. unitPrice is only honoured when
    replaying an OFFLINE sale (the price the till showed at the time) - an
    online sale always uses the server's price.
    """
    productId = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    unitPrice = serializers.DecimalField(min_value=Decimal('0'), required=False, allow_null=True, **MONEY)


class DiscountInputSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['AMOUNT', 'PERCENT'])
    value = serializers.DecimalField(min_value=Decimal('0'), **MONEY)


class PaymentInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=METHOD_CHOICES)
    amount = serializers.DecimalField(min_value=Decimal('0.01'), **MONEY)


class RecordSaleSerializer(serializers.Serializer):
    items = SaleItemInputSerializer(many=True, allow_empty=False, max_length=200)
    discount = DiscountInputSerializer(required=False, allow_null=True)
    customerId = serializers.UUIDField(required=False, allow_null=True)
    # Absent = the old behaviour (paid in full, in cash). Present = exactly
    # these payments; anything not covered is sold on credit.
    payments = PaymentInputSerializer(many=True, required=False, allow_null=True, max_length=10)
    clientId = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=200)


class ReturnItemInputSerializer(serializers.Serializer):
    saleItemId = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)


class ReturnInputSerializer(serializers.Serializer):
    items = ReturnItemInputSerializer(many=True, allow_empty=False, max_length=200)
    refundMethod = serializers.ChoiceField(choices=METHOD_CHOICES + [''], required=False, allow_blank=True, default='')
    restock = serializers.BooleanField(required=False, default=True)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=200, default='')


class CustomerPaymentInputSerializer(serializers.Serializer):
    customerId = serializers.UUIDField()
    amount = serializers.DecimalField(min_value=Decimal('0.01'), **MONEY)
    method = serializers.ChoiceField(choices=METHOD_CHOICES)


class SyncOperationSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=['sale', 'customer_payment'])
    clientId = serializers.UUIDField()
    createdAt = serializers.DateTimeField(required=False, allow_null=True)
    payload = serializers.DictField()


class SyncSerializer(serializers.Serializer):
    operations = SyncOperationSerializer(many=True, allow_empty=False, max_length=50)


class ShiftSerializer(serializers.ModelSerializer):
    opened_by_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Shift
        fields = [
            'id', 'opened_by', 'opened_by_name', 'opened_at', 'opening_float', 'closed_at', 'closed_by_name',
            'expected_cash', 'counted_cash', 'variance', 'notes',
        ]

    def get_opened_by_name(self, obj):
        return obj.opened_by.name

    def get_closed_by_name(self, obj):
        return obj.closed_by.name if obj.closed_by else None
