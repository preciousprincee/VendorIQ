from django.urls import path
from .views import StoreListCreateView, StoreDetailView, StaffListCreateView, StaffDetailView

urlpatterns = [
    path('', StoreListCreateView.as_view()),
    path('<uuid:store_id>/', StoreDetailView.as_view()),
    path('<uuid:store_id>/staff/', StaffListCreateView.as_view()),
    path('<uuid:store_id>/staff/<uuid:staff_id>/', StaffDetailView.as_view()),
]
