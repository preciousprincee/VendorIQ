import pytest


@pytest.mark.django_db
class TestRegisterAndLogin:
    def test_register_creates_user_and_returns_token(self, api_client):
        response = api_client.post('/api/auth/register/', {
            'name': 'New Owner',
            'email': 'newowner@example.com',
            'phone': '08011110001',
            'password': 'Strongpass123!',
        }, format='json')
        assert response.status_code == 201
        assert 'token' in response.data
        assert response.data['user']['email'] == 'newowner@example.com'

    def test_register_rejects_duplicate_email(self, api_client, owner_user):
        response = api_client.post('/api/auth/register/', {
            'name': 'Someone',
            'email': owner_user.email,
            'phone': '08011110002',
            'password': 'Strongpass123!',
        }, format='json')
        assert response.status_code in (400, 409)

    def test_login_with_correct_credentials(self, api_client):
        api_client.post('/api/auth/register/', {
            'name': 'Login Test',
            'email': 'logintest@example.com',
            'phone': '08011110003',
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
            'phone': '08011110004',
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


@pytest.mark.django_db
class TestPhoneAsReferralCode:
    def _register(self, api_client, email, phone='__unset__', referred_by_code=None):
        payload = {'name': 'Person', 'email': email, 'password': 'Strongpass123!'}
        if phone != '__unset__':
            payload['phone'] = phone
        if referred_by_code is not None:
            payload['referred_by_code'] = referred_by_code
        return api_client.post('/api/auth/register/', payload, format='json')

    def test_registering_with_phone_makes_it_the_referral_code(self, api_client):
        response = self._register(api_client, 'a@example.com', phone='+234 801 234 5678')
        assert response.status_code == 201
        assert response.data['user']['phone'] == '08012345678'
        assert response.data['user']['referral_code'] == '08012345678'

    def test_register_without_phone_is_rejected(self, api_client):
        # The phone number is mandatory now (trial anti-abuse + referral code).
        response = self._register(api_client, 'b@example.com')
        assert response.status_code == 400
        assert 'Phone' in response.data['error']
        assert self._register(api_client, 'b2@example.com', phone='').status_code == 400

    def test_register_rejects_invalid_phone(self, api_client):
        assert self._register(api_client, 'c@example.com', phone='12345').status_code == 400

    def test_register_rejects_phone_already_verified_by_someone_else(self, api_client):
        from apps.authentication.models import User
        assert self._register(api_client, 'd@example.com', phone='08012345678').status_code == 201
        User.objects.filter(email='d@example.com').update(phone_verified=True)
        assert self._register(api_client, 'e@example.com', phone='+2348012345678').status_code == 400

    def test_unverified_number_can_be_claimed_by_its_real_owner(self, api_client):
        # Otherwise anyone could register with a stranger's number and lock
        # them out of it permanently.
        from apps.authentication.models import User
        assert self._register(api_client, 'squatter@example.com', phone='08012345678').status_code == 201
        assert self._register(api_client, 'owner@example.com', phone='08012345678').status_code == 201
        assert User.objects.get(email='squatter@example.com').phone is None
        assert User.objects.get(email='owner@example.com').phone == '08012345678'

    def test_signing_up_with_a_referrers_phone_attributes_the_referral(self, api_client):
        from apps.referrals.models import Referral
        self._register(api_client, 'referrer@example.com', phone='08012345678')
        response = self._register(api_client, 'new@example.com', phone='08099999999', referred_by_code='0801 234 5678')
        assert response.status_code == 201
        assert Referral.objects.filter(referrer__email='referrer@example.com', referred_user__email='new@example.com').exists()


@pytest.mark.django_db
class TestEditProfilePhone:
    def test_can_add_and_change_phone_while_unverified(self, owner_client, owner_user):
        response = owner_client.patch('/api/auth/me/', {'name': 'Store Owner', 'phone': '08011112222'}, format='json')
        assert response.status_code == 200
        owner_user.refresh_from_db()
        assert owner_user.phone == '08011112222'
        assert owner_user.referral_code == '08011112222'

        response = owner_client.patch('/api/auth/me/', {'name': 'Store Owner', 'phone': '08033334444'}, format='json')
        assert response.status_code == 200
        owner_user.refresh_from_db()
        assert owner_user.referral_code == '08033334444'  # old code stops working, new one takes over

    def test_cannot_change_phone_once_verified(self, owner_client, owner_user):
        owner_user.phone = '08011112222'
        owner_user.phone_verified = True
        owner_user.save()
        response = owner_client.patch('/api/auth/me/', {'name': 'Store Owner', 'phone': '08033334444'}, format='json')
        assert response.status_code == 400
        assert 'verified' in response.data['error']
        owner_user.refresh_from_db()
        assert owner_user.phone == '08011112222'

    def test_verified_user_can_still_edit_name(self, owner_client, owner_user):
        owner_user.phone = '08011112222'
        owner_user.phone_verified = True
        owner_user.save()
        response = owner_client.patch('/api/auth/me/', {'name': 'New Name', 'phone': '0801 111 2222'}, format='json')
        assert response.status_code == 200
        owner_user.refresh_from_db()
        assert owner_user.name == 'New Name'

    def test_cannot_take_another_users_phone(self, owner_client, owner_user, other_owner_user):
        other_owner_user.phone = '08055556666'
        other_owner_user.save()
        response = owner_client.patch('/api/auth/me/', {'name': 'Store Owner', 'phone': '08055556666'}, format='json')
        assert response.status_code == 400

    def test_invalid_phone_rejected(self, owner_client):
        response = owner_client.patch('/api/auth/me/', {'name': 'Store Owner', 'phone': 'abc'}, format='json')
        assert response.status_code == 400


@pytest.mark.django_db
class TestChangePassword:
    def test_change_password_with_correct_current_password(self, api_client):
        api_client.post('/api/auth/register/', {'name': 'P', 'email': 'pw@example.com', 'password': 'Strongpass123!', 'phone': '08011119999'}, format='json')
        token = api_client.post('/api/auth/login/', {'email': 'pw@example.com', 'password': 'Strongpass123!'}, format='json').data['token']
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = api_client.post('/api/auth/change-password/', {'current_password': 'Strongpass123!', 'new_password': 'Newerpass456!'}, format='json')
        assert response.status_code == 200
        api_client.credentials()
        assert api_client.post('/api/auth/login/', {'email': 'pw@example.com', 'password': 'Newerpass456!'}, format='json').status_code == 200

    def test_wrong_current_password_rejected(self, owner_client):
        response = owner_client.post('/api/auth/change-password/', {'current_password': 'nope', 'new_password': 'Newerpass456!'}, format='json')
        assert response.status_code == 400
