from django.urls import path
from .views import ExpenseListCreateView, ExpenseDetailView, ProfitabilityView, ExportRecordsView

urlpatterns = [
    path('<uuid:store_id>/expenses/', ExpenseListCreateView.as_view()),
    path('<uuid:store_id>/expenses/<uuid:expense_id>/', ExpenseDetailView.as_view()),
    path('<uuid:store_id>/profitability/', ProfitabilityView.as_view()),
    path('<uuid:store_id>/export/', ExportRecordsView.as_view()),
]
