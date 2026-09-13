from django.urls import path
from .views import SubscriptionView, PlansView, UpgradeView, CancelSubscriptionView, ResumeSubscriptionView, TrialView

urlpatterns = [
    path('subscription/', SubscriptionView.as_view()),
    path('plans/', PlansView.as_view()),
    path('upgrade/', UpgradeView.as_view()),
    path('cancel/', CancelSubscriptionView.as_view()),
    path('resume/', ResumeSubscriptionView.as_view()),
    path('trial/start/', TrialView.as_view()),
]
