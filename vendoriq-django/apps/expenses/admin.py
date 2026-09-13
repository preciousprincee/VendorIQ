from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = ['description', 'store', 'category', 'amount', 'is_overhead', 'incurred_on']
    list_filter = ['category', 'is_overhead', 'store']
    search_fields = ['description', 'store__name']
    ordering = ['-incurred_on']
