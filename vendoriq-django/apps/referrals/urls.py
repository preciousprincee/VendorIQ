from django.urls import path
from .views import (
    ReferralStatusView, ReferralSummaryView, RecentCommissionsView, BanksListView,
    ResolveAccountView, PayoutAccountView, PaystackTransferWebhookView,
)

urlpatterns = [
    path('status/', ReferralStatusView.as_view()),
    path('summary/', ReferralSummaryView.as_view()),
    path('commissions/', RecentCommissionsView.as_view()),
    path('banks/', BanksListView.as_view()),
    path('payout-account/', PayoutAccountView.as_view()),
    path('payout-account/resolve/', ResolveAccountView.as_view()),
    path('paystack-webhook/', PaystackTransferWebhookView.as_view()),
]
