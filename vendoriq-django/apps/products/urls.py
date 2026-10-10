from django.urls import path
from .views import ProductListCreateView, ProductDetailView, ProductBarcodeView, ProductRestockView
from .deletion_views import (
    DeletionRequestCreateView, DeletionRequestListView, DeletionRequestApproveView,
    DeletionRequestRejectView, DeletionRequestCancelView,
)

urlpatterns = [
    path('<uuid:store_id>/products/', ProductListCreateView.as_view()),
    path('<uuid:store_id>/products/barcode/', ProductBarcodeView.as_view()),
    path('<uuid:store_id>/products/<uuid:product_id>/', ProductDetailView.as_view()),
    path('<uuid:store_id>/products/<uuid:product_id>/restock/', ProductRestockView.as_view()),
    path('<uuid:store_id>/products/<uuid:product_id>/deletion-request/', DeletionRequestCreateView.as_view()),
    path('<uuid:store_id>/deletion-requests/', DeletionRequestListView.as_view()),
    path('<uuid:store_id>/deletion-requests/<uuid:request_id>/approve/', DeletionRequestApproveView.as_view()),
    path('<uuid:store_id>/deletion-requests/<uuid:request_id>/reject/', DeletionRequestRejectView.as_view()),
    path('<uuid:store_id>/deletion-requests/<uuid:request_id>/cancel/', DeletionRequestCancelView.as_view()),
]
