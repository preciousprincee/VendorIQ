from django.urls import path
from .views import DashboardView, TrendView, NotificationsView

urlpatterns = [
    path('<uuid:store_id>/insights/dashboard/', DashboardView.as_view()),
    path('<uuid:store_id>/insights/trend/', TrendView.as_view()),
    path('<uuid:store_id>/insights/notifications/', NotificationsView.as_view()),
]
