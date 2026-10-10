from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Sale, SaleItem, SalePayment, SaleReturn, Shift


class SaleItemInline(TabularInline):
    model = SaleItem
    extra = 0


class SalePaymentInline(TabularInline):
    model = SalePayment
    extra = 0
    fields = ['method', 'amount', 'recorded_by', 'customer_payment', 'created_at']
    readonly_fields = fields


@admin.register(Sale)
class SaleAdmin(ModelAdmin):
    list_display = ['id', 'store', 'recorded_by', 'customer', 'total_amount', 'discount_amount', 'amount_paid', 'needs_review', 'created_at']
    list_filter = ['store', 'needs_review']
    search_fields = ['id', 'client_id', 'customer__name']
    inlines = [SaleItemInline, SalePaymentInline]


@admin.register(SaleReturn)
class SaleReturnAdmin(ModelAdmin):
    list_display = ['created_at', 'sale', 'return_value', 'refund_amount', 'refund_method', 'recorded_by']
    list_filter = ['refund_method', 'restocked']
    readonly_fields = ['sale', 'recorded_by', 'created_at']


@admin.register(Shift)
class ShiftAdmin(ModelAdmin):
    list_display = ['store', 'opened_by', 'opened_at', 'closed_at', 'opening_float', 'expected_cash', 'counted_cash', 'variance']
    list_filter = ['store']
    readonly_fields = ['store', 'opened_by', 'opened_at', 'closed_by', 'closed_at', 'expected_cash', 'counted_cash', 'variance']
