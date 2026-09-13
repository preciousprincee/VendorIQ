from django.urls import path
from .views import SaleListCreateView, SaleDetailView

urlpatterns = [
    path('<uuid:store_id>/sales/', SaleListCreateView.as_view()),
    path('<uuid:store_id>/sales/<uuid:sale_id>/', SaleDetailView.as_view()),
]
