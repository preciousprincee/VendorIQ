from rest_framework import serializers
from .images import optimize_photo, PhotoError
from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.ReadOnlyField()
    profit_margin = serializers.ReadOnlyField()
    potential_profit = serializers.SerializerMethodField()
    photo = serializers.ImageField(required=False, allow_null=True, use_url=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'barcode', 'cost_price', 'selling_price',
            'quantity', 'low_stock_threshold', 'category', 'supplier', 'photo', 'is_low_stock',
            'profit_margin', 'potential_profit', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Cost price (and anything derived from it) is what the owner paid
        # suppliers - financial data cashiers don't get, same rule the list
        # summary and sales views already apply.
        if self.context.get('role') == 'CASHIER':
            for key in ('cost_price', 'profit_margin', 'potential_profit'):
                data.pop(key, None)
        return data

    def validate_photo(self, value):
        # One small photo per product. The web app already shrinks pictures
        # before upload, but that is a convenience, not a boundary: anyone
        # calling the API directly skips it. So the server enforces the size
        # cap, checks it really is an image, and re-encodes it small (which
        # also strips location metadata). See apps/products/images.py.
        if not value:
            return value
        try:
            return optimize_photo(value)
        except PhotoError as exc:
            raise serializers.ValidationError(str(exc))

    # None of cost_price/selling_price/quantity/low_stock_threshold had any
    # validation at all before this - neither here nor as a DB-level
    # constraint (they're plain DecimalField/IntegerField, not
    # PositiveIntegerField). A negative selling_price or quantity wouldn't
    # just look odd on the product list - fed into a sale, unit_price *
    # quantity produces a negative total_amount that flows straight into
    # the store's revenue/profit aggregates, silently corrupting them (see
    # the matching fix in apps/sales/serializers.py, which closes the other
    # half of this - a negative sale QUANTITY - at the point of sale
    # itself). ExpenseSerializer already validates amount > 0 the same way;
    # this brings Product in line with that existing convention.
    def validate_cost_price(self, value):
        if value < 0:
            raise serializers.ValidationError('Cost price cannot be negative.')
        return value

    def validate_selling_price(self, value):
        if value < 0:
            raise serializers.ValidationError('Selling price cannot be negative.')
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError('Quantity cannot be negative.')
        return value

    def validate_low_stock_threshold(self, value):
        if value < 0:
            raise serializers.ValidationError('Low stock threshold cannot be negative.')
        return value

    def get_potential_profit(self, obj):
        return float((obj.selling_price - obj.cost_price) * obj.quantity)
