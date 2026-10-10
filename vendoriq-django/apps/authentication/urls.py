from django.urls import path
from .views import RegisterView, LoginView, MeView, ChangePasswordView, RefreshTokenView, LogoutView
from .verification_views import SendEmailCodeView, ConfirmEmailCodeView, SendPhoneCodeView, ConfirmPhoneCodeView
from .social_views import GoogleLoginView

urlpatterns = [
    path('register/', RegisterView.as_view()),
    path('login/', LoginView.as_view()),
    path('me/', MeView.as_view()),
    path('change-password/', ChangePasswordView.as_view()),
    path('social/google/', GoogleLoginView.as_view()),
    path('token/refresh/', RefreshTokenView.as_view()),
    path('logout/', LogoutView.as_view()),
    path('verify/email/send/', SendEmailCodeView.as_view()),
    path('verify/email/confirm/', ConfirmEmailCodeView.as_view()),
    path('verify/phone/send/', SendPhoneCodeView.as_view()),
    path('verify/phone/confirm/', ConfirmPhoneCodeView.as_view()),
]
