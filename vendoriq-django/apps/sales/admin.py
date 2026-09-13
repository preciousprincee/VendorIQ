from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Sale, SaleItem


class SaleItemInline(TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(ModelAdmin):
    list_display = ['id', 'store', 'recorded_by', 'total_amount', 'total_profit', 'created_at']
    list_filter = ['store']
    inlines = [SaleItemInline]
