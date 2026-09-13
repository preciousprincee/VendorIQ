import pytest


@pytest.mark.django_db
class TestRegisterAndLogin:
    def test_register_creates_user_and_returns_token(self, api_client):
        response = api_client.post('/api/auth/register/', {
            'name': 'New Owner',
            'email': 'newowner@example.com',
            'password': 'Strongpass123!',
        }, format='json')
        assert response.status_code == 201
        assert 'token' in response.data
        assert response.data['user']['email'] == 'newowner@example.com'

    def test_register_rejects_duplicate_email(self, api_client, owner_user):
        response = api_client.post('/api/auth/register/', {
            'name': 'Someone',
            'email': owner_user.email,
            'password': 'Strongpass123!',
        }, format='json')
        assert response.status_code in (400, 409)

    def test_login_with_correct_credentials(self, api_client):
        api_client.post('/api/auth/register/', {
            'name': 'Login Test',
            'email': 'logintest@example.com',
            'password': 'Strongpass123!',
        }, format='json')
        response = api_client.post('/api/auth/login/', {
            'email': 'logintest@example.com',
            'password': 'Strongpass123!',
        }, format='json')
        assert response.status_code == 200
        assert 'token' in response.data

    def test_login_with_wrong_password_is_rejected(self, api_client):
        api_client.post('/api/auth/register/', {
            'name': 'Login Test',
            'email': 'logintest2@example.com',
            'password': 'Strongpass123!',
        }, format='json')
        response = api_client.post('/api/auth/login/', {
            'email': 'logintest2@example.com',
            'password': 'wrong-password',
        }, format='json')
        assert response.status_code == 401

    def test_unauthenticated_request_is_rejected(self, api_client, store):
        # No force_authenticate - this is what an anonymous request looks like.
        response = api_client.get(f'/api/stores/{store.id}/products/')
        assert response.status_code == 401


@pytest.mark.django_db
class TestLoginEventTracking:
    """
    Login/device history - every login attempt (success or failure) should
    leave a record, since this is what the admin's per-user login history
    is built from.
    """

    def test_successful_login_creates_login_event(self, api_client, owner_user):
        from apps.authentication.models import LoginEvent
        api_client.post('/api/auth/login/', {
            'email': owner_user.email, 'password': 'Testpass123!',
        }, format='json')
        event = LoginEvent.objects.filter(user=owner_user).first()
        assert event is not None
        assert event.success is True
        assert event.email_attempted == owner_user.email

    def test_wrong_password_creates_failed_login_event_attached_to_user(self, api_client, owner_user):
        from apps.authentication.models import LoginEvent
        api_client.post('/api/auth/login/', {
            'email': owner_user.email, 'password': 'wrong-password',
        }, format='json')
        event = LoginEvent.objects.filter(email_attempted=owner_user.email, success=False).first()
        assert event is not None
        # Still attached to the real user (we know which account it is from
        # the email) so a pattern of failures shows up on their page.
        assert event.user_id == owner_user.id

    def test_unknown_email_creates_login_event_with_no_user(self, api_client):
        from apps.authentication.models import LoginEvent
        api_client.post('/api/auth/login/', {
            'email': 'nobody-registered@example.com', 'password': 'whatever123',
        }, format='json')
        event = LoginEvent.objects.filter(email_attempted='nobody-registered@example.com').first()
        assert event is not None
        assert event.success is False
        assert event.user is None

    def test_login_event_records_device_info_from_user_agent(self, api_client, owner_user):
        from apps.authentication.models import LoginEvent
        api_client.post(
            '/api/auth/login/',
            {'email': owner_user.email, 'password': 'Testpass123!'},
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36',
        )
        event = LoginEvent.objects.filter(user=owner_user).first()
        assert event.device_type == 'Desktop'
        assert event.browser == 'Chrome'
        assert event.os == 'Windows'
