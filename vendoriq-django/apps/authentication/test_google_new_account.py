"""
GoogleLoginView tells the frontend whether THIS request created the account, so product analytics can
record "sign_up" vs "login". Tested at the view level (the Google token exchange itself is allauth's job).
"""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.authentication.models import User
from apps.authentication.social_views import GoogleLoginView


def _response_for(user):
    raw = APIRequestFactory().post('/api/auth/social/google/', {}, format='json')
    view = GoogleLoginView()
    view.request = Request(raw, parsers=[JSONParser()])
    view.user = user
    return view.get_response()


@pytest.mark.django_db
class TestIsNewAccountFlag:
    def test_a_just_created_account_is_flagged_new(self):
        user = User.objects.create_user(email='g-new@example.com', name='G', password=None)
        r = _response_for(user)
        assert r.status_code == 200
        assert r.data['isNewAccount'] is True
        assert 'refresh' not in r.data                 # still no refresh token in the body

    def test_an_older_account_is_not_new(self):
        user = User.objects.create_user(email='g-old@example.com', name='G', password=None)
        User.objects.filter(pk=user.pk).update(created_at=timezone.now() - timedelta(minutes=3))
        user.refresh_from_db()
        assert _response_for(user).data['isNewAccount'] is False

    def test_the_response_still_sets_the_session_cookie(self):
        user = User.objects.create_user(email='g-cookie@example.com', name='G', password=None)
        assert _response_for(user).cookies['viq_refresh']['httponly'] is True
