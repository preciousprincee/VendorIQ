from django.urls import path
from .views import ChatView, ChatHistoryView

urlpatterns = [
    path('chat/', ChatView.as_view()),
    path('<uuid:store_id>/history/', ChatHistoryView.as_view()),
]
