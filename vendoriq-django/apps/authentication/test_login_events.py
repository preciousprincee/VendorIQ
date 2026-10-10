"""
LoginEvent (login history + brute-force lockout) must have a real table. A missing migration used to
make every login answer 500 on a fresh database.
"""
import pytest
from django.db import connection

from apps.authentication.models import LoginEvent


@pytest.mark.django_db
class TestLoginEventTable:
    def test_the_table_exists_after_migrating(self):
        assert LoginEvent._meta.db_table in connection.introspection.table_names()

    def test_register_login_and_a_failed_login_are_recorded(self, api_client):
        api_client.post('/api/auth/register/', {'name': 'L', 'email': 'le@example.com', 'phone': '08035550001', 'password': 'Strongpass123!'}, format='json')
        ok = api_client.post('/api/auth/login/', {'email': 'le@example.com', 'password': 'Strongpass123!'}, format='json')
        bad = api_client.post('/api/auth/login/', {'email': 'le@example.com', 'password': 'wrong-password'}, format='json')
        assert ok.status_code == 200 and bad.status_code == 401
        assert LoginEvent.objects.filter(email_attempted='le@example.com', success=True).count() == 1
        assert LoginEvent.objects.filter(email_attempted='le@example.com', success=False).count() == 1
