from django.urls import path

from .views import NotificationListView, NotificationSeenView

urlpatterns = [
    path('', NotificationListView.as_view()),
    path('seen/', NotificationSeenView.as_view()),
]
