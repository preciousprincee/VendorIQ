from django.urls import path
from .views import (
    SaleListCreateView, SaleDetailView, SaleReturnView, SaleReviewView, SyncView, CatalogView,
    ShiftListView, CurrentShiftView, OpenShiftView, ShiftDetailView, CloseShiftView, DailyReportView,
)

urlpatterns = [
    path('<uuid:store_id>/sales/', SaleListCreateView.as_view()),
    path('<uuid:store_id>/sales/<uuid:sale_id>/', SaleDetailView.as_view()),
    path('<uuid:store_id>/sales/<uuid:sale_id>/returns/', SaleReturnView.as_view()),
    path('<uuid:store_id>/sales/<uuid:sale_id>/review/', SaleReviewView.as_view()),
    path('<uuid:store_id>/sync/', SyncView.as_view()),
    path('<uuid:store_id>/catalog/', CatalogView.as_view()),
    path('<uuid:store_id>/shifts/', ShiftListView.as_view()),
    path('<uuid:store_id>/shifts/current/', CurrentShiftView.as_view()),
    path('<uuid:store_id>/shifts/open/', OpenShiftView.as_view()),
    path('<uuid:store_id>/shifts/<uuid:shift_id>/', ShiftDetailView.as_view()),
    path('<uuid:store_id>/shifts/<uuid:shift_id>/close/', CloseShiftView.as_view()),
    path('<uuid:store_id>/reports/daily/', DailyReportView.as_view()),
]
