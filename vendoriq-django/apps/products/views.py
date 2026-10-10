from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models import Sum, F, Q, Count, DecimalField
from django.db.models.deletion import ProtectedError
from . import deletion
from .models import Product
from .serializers import ProductSerializer
from apps.stores.models import Store
from apps.stores.base_views import StoreScopedAPIView
from apps.stores.permissions import require_store_access
from apps.billing.entitlements import check_can_add_product
from vendoriq.cache_utils import invalidate_store_insights


class ProductListCreateView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view/add products

    def get(self, request, store_id):
        store = self.store
        role = self.role
        search = request.query_params.get('search', '')
        products = Product.objects.filter(store=store)
        if search:
            products = products.filter(Q(name__icontains=search) | Q(barcode__icontains=search))
        products = products.order_by('name')

        # Aggregate in the database rather than pulling every row into Python -
        # this is the difference between one small query and hydrating an
        # entire catalog's worth of model instances on every page load, which
        # is what actually falls over first under concurrent traffic.
        agg = products.aggregate(
            total_stock_value=Sum(F('cost_price') * F('quantity'), output_field=DecimalField()),
            total_retail_value=Sum(F('selling_price') * F('quantity'), output_field=DecimalField()),
            low_stock_count=Count('id', filter=Q(quantity__lte=F('low_stock_threshold'))),
            out_of_stock_count=Count('id', filter=Q(quantity=0)),
            total=Count('id'),
        )
        total_stock_value = float(agg['total_stock_value'] or 0)
        total_retail_value = float(agg['total_retail_value'] or 0)

        summary = {
            'total': agg['total'],
            'lowStockCount': agg['low_stock_count'],
            'outOfStockCount': agg['out_of_stock_count'],
        }
        # Stock/retail value reveal cost price in aggregate and are financial
        # data - only owners and managers see them. Cashiers still get counts.
        if role in ('OWNER', 'MANAGER'):
            summary['totalStockValue'] = total_stock_value
            summary['totalRetailValue'] = total_retail_value
            summary['potentialProfit'] = total_retail_value - total_stock_value

        # Aggregates above already ran against the full queryset - only the
        # actual row serialization is capped. Without this, a store with a
        # very large catalog turns every plain product-list request (no
        # search term) into hydrating and JSON-serializing its entire
        # inventory, which is real memory/CPU cost per request. Under
        # thousands of concurrent requests that's exactly the kind of thing
        # that OOMs a worker rather than just being "a bit slow". Search
        # narrows results anyway, so this only bites the unfiltered view.
        PRODUCT_LIST_CAP = 500
        truncated = agg['total'] > PRODUCT_LIST_CAP
        serializer = ProductSerializer(products[:PRODUCT_LIST_CAP], many=True, context={'role': role})
        return Response({
            'products': serializer.data,
            'summary': summary,
            'truncated': truncated,
        })

    def post(self, request, store_id):
        serializer = ProductSerializer(data=request.data, context={'role': self.role})
        if not serializer.is_valid():
            return Response({'error': next(iter(serializer.errors.values()))[0]}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            # Lock the store row for the check+create so two concurrent
            # "add product" requests (a double-tap, two open tabs, a retried
            # request) can't both pass check_can_add_product's count check
            # before either has actually created their product. Without
            # this, a Free-plan store sitting right at its 100-product
            # limit could briefly end up with 101+, since the original
            # count-then-create had no atomicity tying them together.
            Store.objects.select_for_update().get(id=self.store.id)
            check_can_add_product(self.store)
            product = serializer.save(store=self.store)
        invalidate_store_insights(store_id)
        return Response({'product': ProductSerializer(product, context={'role': self.role}).data}, status=status.HTTP_201_CREATED)


class ProductDetailView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view/edit; delete narrows further below

    def get_product(self, product_id):
        try:
            return Product.objects.get(id=product_id, store=self.store)
        except Product.DoesNotExist:
            return None

    def get(self, request, store_id, product_id):
        product = self.get_product(product_id)
        if not product:
            return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'product': ProductSerializer(product, context={'role': self.role}).data})

    def patch(self, request, store_id, product_id):
        product = self.get_product(product_id)
        if not product:
            return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
        # A cashier rings up sales - they don't get to re-price the catalogue
        # or rewrite the cost the profit figures are computed from.
        if self.role == 'CASHIER' and ('cost_price' in request.data or 'selling_price' in request.data):
            return Response({'error': 'You do not have permission to change prices.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProductSerializer(product, data=request.data, partial=True, context={'role': self.role})
        if serializer.is_valid():
            serializer.save()
            invalidate_store_insights(store_id)
            return Response({'product': serializer.data})
        return Response({'error': next(iter(serializer.errors.values()))[0]}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, store_id, product_id):
        require_store_access(self.store, request.user, ['OWNER', 'MANAGER'])
        product = self.get_product(product_id)
        if not product:
            return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            deletion.delete_directly(product, request.user)
        except ProtectedError:
            # SaleItem.product and InvoiceItem.product are on_delete=PROTECT
            # (financial records shouldn't silently disappear or point at
            # nothing) - so a product that's ever been sold or invoiced
            # can't actually be hard-deleted. Without this catch, that's a
            # raw unhandled ProtectedError -> 500 with no explanation, for
            # what is honestly the COMMON case (most products worth
            # deleting have at least one sale against them). Point the
            # owner at the real alternative instead of a confusing crash.
            return Response(
                {'error': "This product has sales or invoice history and can't be deleted, since that would break those records. Set its stock to 0 or rename it to \"discontinued\" instead."},
                status=status.HTTP_409_CONFLICT,
            )
        invalidate_store_insights(store_id)
        return Response({'message': 'Product deleted.'})


class ProductBarcodeView(StoreScopedAPIView):
    def get(self, request, store_id):
        barcode = request.query_params.get('barcode')
        if not barcode:
            return Response({'error': 'Barcode is required.'}, status=status.HTTP_400_BAD_REQUEST)
        # Barcodes aren't unique per store, so .get() raised
        # MultipleObjectsReturned (a 500 at the till) for a duplicate.
        product = Product.objects.filter(store=self.store, barcode=barcode).order_by('created_at').first()
        if product is None:
            return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'product': ProductSerializer(product, context={'role': self.role}).data})


class ProductRestockView(StoreScopedAPIView):
    def patch(self, request, store_id, product_id):
        qty = request.data.get('quantity', 0)
        # bool is a subclass of int: `true` would restock 1 unit.
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0 or qty > 1_000_000:
            return Response({'error': 'Quantity must be a positive integer.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            # Lock the row: a plain read-modify-write here lost updates when
            # a sale (which locks) landed between the read and the save.
            try:
                product = Product.objects.select_for_update().get(id=product_id, store=self.store)
            except Product.DoesNotExist:
                return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
            product.quantity += qty
            product.save(update_fields=['quantity', 'updated_at'])
        invalidate_store_insights(store_id)
        return Response({'product': ProductSerializer(product, context={'role': self.role}).data})
