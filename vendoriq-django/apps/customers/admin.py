from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Customer, CustomerPayment


@admin.register(Customer)
class CustomerAdmin(ModelAdmin):
    list_display = ['name', 'store', 'phone', 'email', 'created_at']
    list_filter = ['store']
    search_fields = ['name', 'phone', 'email']


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(ModelAdmin):
    list_display = ['created_at', 'customer', 'store', 'amount', 'method', 'recorded_by']
    list_filter = ['method', 'store']
    readonly_fields = ['store', 'customer', 'amount', 'method', 'recorded_by', 'client_id', 'created_at']

    def has_add_permission(self, request):
        return False
