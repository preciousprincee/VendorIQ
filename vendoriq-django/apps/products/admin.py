from django.contrib import admin
from django.db.models import Sum, F
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from .models import Product, ProductDeletionRequest


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ['name', 'store', 'category', 'cost_price', 'selling_price', 'quantity', 'low_stock_threshold']
    search_fields = ['name', 'store__name', 'supplier']
    list_filter = ['store', 'category']
    readonly_fields = ['performance_panel', 'created_at']
    fieldsets = (
        (None, {'fields': ('store', 'name', 'barcode', 'category', 'supplier')}),
        ('Pricing & stock', {'fields': ('cost_price', 'selling_price', 'quantity', 'low_stock_threshold', 'photo')}),
        ('Sales performance', {'fields': ('performance_panel',)}),
        ('Timestamps', {'fields': ('created_at',)}),
    )

    @admin.display(description='Sales performance (all time)')
    def performance_panel(self, obj):
        # Queried directly rather than via the reverse accessor (SaleItem.product
        # has no related_name, so Django's default `saleitem_set` name is easy
        # to mistype/forget) - explicit and unambiguous instead.
        from apps.sales.models import SaleItem
        agg = SaleItem.objects.filter(product=obj).aggregate(
            units_sold=Sum(F('quantity') - F('returned_quantity')),
            revenue=Sum(F('unit_price') * F('quantity')),
            profit=Sum('profit'),
        )
        units_sold = agg['units_sold'] or 0
        revenue = agg['revenue'] or 0
        profit = agg['profit'] or 0
        avg_price = (revenue / units_sold) if units_sold else 0
        return format_html(
            '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;max-width:640px;">'
            '<div><div style="font-size:11px;color:#888;">Units sold</div><div style="font-size:18px;font-weight:700;">{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Revenue generated</div><div style="font-size:18px;font-weight:700;">₦{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Profit generated</div><div style="font-size:18px;font-weight:700;">₦{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Avg selling price</div><div style="font-size:18px;font-weight:700;">₦{}</div></div>'
            '</div>',
            units_sold, f'{revenue:,.0f}', f'{profit:,.0f}', f'{avg_price:,.0f}',
        )


@admin.register(ProductDeletionRequest)
class ProductDeletionRequestAdmin(ModelAdmin):
    """Audit trail of cashier requests to delete products: who asked, why, who decided."""
    list_display = ['created_at', 'store', 'product_name', 'requested_by', 'status', 'decided_by', 'decided_at']
    list_filter = ['status', 'store']
    search_fields = ['product_name', 'remark', 'requested_by__email']
    readonly_fields = ['store', 'product', 'product_name', 'requested_by', 'remark', 'status', 'decided_by', 'decided_at', 'decision_note', 'created_at']

    def has_add_permission(self, request):
        return False
