import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestEmailCaseInsensitivity:
    def _register(self, client, email, phone='08022220001'):
        return client.post('/api/auth/register/', {'name': 'X', 'email': email, 'phone': phone, 'password': 'Strongpass123!'}, format='json')

    def test_cannot_register_the_same_email_in_a_different_case(self, api_client):
        assert self._register(api_client, 'case@example.com').status_code == 201
        assert self._register(api_client, 'CASE@Example.com', phone='08022220009').status_code == 400

    def test_login_works_regardless_of_email_case(self, api_client):
        self._register(api_client, 'mixed@example.com')
        response = api_client.post('/api/auth/login/', {'email': 'MiXeD@Example.COM', 'password': 'Strongpass123!'}, format='json')
        assert response.status_code == 200
        assert 'token' in response.data


@pytest.mark.django_db
class TestPasswordChangeInvalidatesTokens:
    def test_old_token_stops_working_and_new_one_works(self, api_client):
        reg = api_client.post('/api/auth/register/', {'name': 'X', 'email': 'pw@example.com', 'phone': '08022220002', 'password': 'Strongpass123!'}, format='json')
        old_token = reg.data['token']

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_token}')
        assert client.get('/api/auth/me/').status_code == 200

        change = client.post('/api/auth/change-password/', {
            'current_password': 'Strongpass123!', 'new_password': 'Anotherpass456!',
        }, format='json')
        assert change.status_code == 200
        new_token = change.data['token']

        assert client.get('/api/auth/me/').status_code == 401  # old token is dead

        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f'Bearer {new_token}')
        assert fresh.get('/api/auth/me/').status_code == 200
