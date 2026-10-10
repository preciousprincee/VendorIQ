from django.urls import path
from .views import CustomerListCreateView, CustomerDetailView, CustomerStatementView, CustomerPaymentView

urlpatterns = [
    path('<uuid:store_id>/customers/', CustomerListCreateView.as_view()),
    path('<uuid:store_id>/customers/<uuid:customer_id>/', CustomerDetailView.as_view()),
    path('<uuid:store_id>/customers/<uuid:customer_id>/statement/', CustomerStatementView.as_view()),
    path('<uuid:store_id>/customers/<uuid:customer_id>/payments/', CustomerPaymentView.as_view()),
]
