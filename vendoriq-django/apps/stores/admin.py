from django.contrib import admin
from django.db.models import Sum, Count
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from .models import Store, Staff


class StaffInline(TabularInline):
    model = Staff
    extra = 0
    autocomplete_fields = []


@admin.register(Store)
class StoreAdmin(ModelAdmin):
    list_display = ['name', 'owner', 'location', 'health_badge', 'created_at']
    list_filter = ['owner']
    search_fields = ['name', 'owner__email']
    inlines = [StaffInline]
    readonly_fields = ['summary_panel', 'created_at', 'updated_at']
    fieldsets = (
        (None, {'fields': ('name', 'owner', 'location')}),
        ('At a glance', {'fields': ('summary_panel',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        # These annotations back both the list "health" badge and the detail
        # page summary without N+1 queries per row.
        return super().get_queryset(request).annotate(
            _sale_count=Count('sales', distinct=True),
            _revenue=Sum('sales__total_amount'),
            _sales_profit=Sum('sales__total_profit'),
            _expenses=Sum('expenses__amount'),
            _product_count=Count('products', distinct=True),
            _staff_count=Count('staff', distinct=True),
        )

    @admin.display(description='Health')
    def health_badge(self, obj):
        from datetime import timedelta
        from django.utils import timezone
        from apps.sales.models import Sale
        has_recent_sale = Sale.objects.filter(store=obj, created_at__gte=timezone.now() - timedelta(days=30)).exists()
        if has_recent_sale:
            return format_html('<span style="color:#16a34a;font-weight:600;">● Active</span>')
        has_any_sale = obj._sale_count and obj._sale_count > 0
        if has_any_sale:
            return format_html('<span style="color:#d97706;font-weight:600;">● At risk</span>')
        return format_html('<span style="color:#9ca3af;font-weight:600;">● No sales yet</span>')

    @admin.display(description='Summary')
    def summary_panel(self, obj):
        revenue = obj._revenue or 0
        sales_profit = obj._sales_profit or 0
        expenses = obj._expenses or 0
        net_profit = float(sales_profit) - float(expenses)
        return format_html(
            '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;max-width:640px;">'
            '<div><div style="font-size:11px;color:#888;">Revenue (all time)</div><div style="font-size:18px;font-weight:700;">₦{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Net profit (all time)</div><div style="font-size:18px;font-weight:700;">₦{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Total sales</div><div style="font-size:18px;font-weight:700;">{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Products</div><div style="font-size:18px;font-weight:700;">{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Staff</div><div style="font-size:18px;font-weight:700;">{}</div></div>'
            '<div><div style="font-size:11px;color:#888;">Total expenses</div><div style="font-size:18px;font-weight:700;">₦{}</div></div>'
            '</div>',
            f'{revenue:,.0f}', f'{net_profit:,.0f}', obj._sale_count or 0,
            obj._product_count or 0, obj._staff_count or 0, f'{expenses:,.0f}',
        )


@admin.register(Staff)
class StaffAdmin(ModelAdmin):
    list_display = ['user', 'store', 'role', 'created_at']
    list_filter = ['role', 'store']
    search_fields = ['user__email', 'store__name']
