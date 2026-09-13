from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline
from .models import Invoice, InvoiceItem


class InvoiceItemInline(TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = ['customer_name', 'store', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'store']
    inlines = [InvoiceItemInline]
