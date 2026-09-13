from rest_framework.response import Response
from rest_framework import status
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from .models import Sale, SaleItem
from .serializers import SaleSerializer, RecordSaleSerializer
from apps.stores.base_views import StoreScopedAPIView
from apps.stores.models import Staff
from apps.products.models import Product
from vendoriq.cache_utils import invalidate_store_insights


class SaleListCreateView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view/record sales

    def get(self, request, store_id):
        store = self.store
        sales = Sale.objects.filter(store=store).select_related('recorded_by').prefetch_related('sale_items__product').order_by('-created_at')[:50]

        response_data = {'sales': SaleSerializer(sales, many=True).data}

        # Cashiers can record and view sales, but revenue/profit totals are
        # financial data reserved for owners and managers.
        if self.role in ('OWNER', 'MANAGER'):
            all_sales = Sale.objects.filter(store=store)
            total = all_sales.aggregate(
                revenue=Sum('total_amount'),
                profit=Sum('total_profit')
            )
            response_data['summary'] = {
                'totalRevenue': float(total['revenue'] or 0),
                'totalProfit': float(total['profit'] or 0),
                'totalTransactions': all_sales.count(),
            }

        return Response(response_data)

    def post(self, request, store_id):
        store = self.store
        serializer = RecordSaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': 'Invalid data.'}, status=status.HTTP_400_BAD_REQUEST)

        items = serializer.validated_data['items']

        try:
            staff = Staff.objects.get(store=store, user=request.user)
        except Staff.DoesNotExist:
            staff = None

        try:
            with transaction.atomic():
                # Decimal arithmetic throughout - product.selling_price/
                # cost_price come from a DecimalField, and Sale/SaleItem's
                # total_amount/total_profit/unit_price/unit_cost/profit
                # columns are ALL DecimalFields too (exact, no binary
                # floating-point rounding). Converting to float() here (as
                # this used to do) would do the actual money math in
                # binary floating point - which cannot represent most
                # decimal fractions exactly (e.g. 0.1 + 0.2 != 0.3 in
                # float) - before saving the result back into an exact
                # Decimal column, silently baking a few kobo of drift into
                # the recorded sale on every transaction. Only ever
                # converted to float at the very end, for the JSON API
                # response - never for anything that gets persisted.
                total_amount = Decimal('0')
                total_profit = Decimal('0')
                sale_items_data = []

                for item in items:
                    # Both keys are now guaranteed present and valid -
                    # productId a real UUID, quantity a positive int - by
                    # RecordSaleSerializer/SaleItemInputSerializer (see
                    # apps/sales/serializers.py). No more .get(..., 0)
                    # fallback: that silent default, combined with no
                    # positivity check, used to be exactly how a missing or
                    # negative quantity could slip through into the stock/
                    # revenue math below undetected.
                    product_id = item['productId']
                    quantity = item['quantity']

                    try:
                        product = Product.objects.select_for_update().get(id=product_id, store=store)
                    except Product.DoesNotExist:
                        return Response({'error': f'Product not found.'}, status=status.HTTP_404_NOT_FOUND)

                    if product.quantity < quantity:
                        return Response(
                            {'error': f'Insufficient stock for {product.name}. Available: {product.quantity}'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    unit_price = product.selling_price
                    unit_cost = product.cost_price
                    item_profit = (unit_price - unit_cost) * quantity
                    item_amount = unit_price * quantity

                    total_amount += item_amount
                    total_profit += item_profit

                    sale_items_data.append({
                        'product': product,
                        'quantity': quantity,
                        'unit_price': unit_price,
                        'unit_cost': unit_cost,
                        'profit': item_profit,
                    })

                    product.quantity -= quantity
                    product.save()

                sale = Sale.objects.create(
                    store=store,
                    staff=staff,
                    recorded_by=request.user,
                    total_amount=total_amount,
                    total_profit=total_profit,
                )

                for item_data in sale_items_data:
                    SaleItem.objects.create(sale=sale, **item_data)

                sale.refresh_from_db()
                invalidate_store_insights(store_id)
                return Response({'sale': SaleSerializer(sale).data}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SaleDetailView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view a sale; delete narrows further below

    def get(self, request, store_id, sale_id):
        try:
            sale = Sale.objects.prefetch_related('sale_items__product').get(id=sale_id, store=self.store)
            return Response({'sale': SaleSerializer(sale).data})
        except Sale.DoesNotExist:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, store_id, sale_id):
        # Deleting a sale record (e.g. it was entered by mistake) restores the
        # stock it deducted, so inventory numbers stay accurate. Owners/managers
        # can delete any sale; cashiers can only delete sales they personally
        # recorded, so one cashier can't erase another's till record.
        try:
            sale = Sale.objects.prefetch_related('sale_items__product').get(id=sale_id, store=self.store)
        except Sale.DoesNotExist:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)

        if self.role == 'CASHIER' and sale.recorded_by_id != request.user.id:
            return Response({'error': 'You can only delete sales you recorded yourself.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            for item in sale.sale_items.all():
                product = Product.objects.select_for_update().get(id=item.product_id)
                product.quantity += item.quantity
                product.save()
            sale.delete()

        invalidate_store_insights(store_id)
        return Response({'message': 'Sale deleted and stock restored.'})
