from django.urls import path
from .views import ProductListCreateView, ProductDetailView, ProductBarcodeView, ProductRestockView

urlpatterns = [
    path('<uuid:store_id>/products/', ProductListCreateView.as_view()),
    path('<uuid:store_id>/products/barcode/', ProductBarcodeView.as_view()),
    path('<uuid:store_id>/products/<uuid:product_id>/', ProductDetailView.as_view()),
    path('<uuid:store_id>/products/<uuid:product_id>/restock/', ProductRestockView.as_view()),
]
