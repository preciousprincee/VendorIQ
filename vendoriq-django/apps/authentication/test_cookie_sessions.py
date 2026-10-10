"""
The refresh token lives in an HttpOnly cookie - never in the JSON body, where page scripts could read it.
"""
import pytest
from rest_framework.test import APIClient

from apps.authentication.cookies import new_refresh_token
from apps.authentication.models import User

CSRF = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
REFRESH = '/api/auth/token/refresh/'
COOKIE = 'viq_refresh'
THIRTY_DAYS = 30 * 24 * 3600


def _register(client, email='cookie@example.com', phone='08033330001'):
    return client.post('/api/auth/register/', {'name': 'C', 'email': email, 'phone': phone, 'password': 'Strongpass123!'}, format='json')


def _login(client, email='cookie@example.com'):
    return client.post('/api/auth/login/', {'email': email, 'password': 'Strongpass123!'}, format='json')


@pytest.mark.django_db
class TestCookieIsIssuedSafely:
    def test_login_sets_an_httponly_cookie_and_the_body_has_no_refresh_token(self, api_client):
        _register(api_client)
        r = _login(api_client)
        assert r.status_code == 200 and 'token' in r.data
        assert 'refresh' not in r.data                       # nothing long-lived is readable by page scripts
        morsel = r.cookies[COOKIE]
        assert morsel['httponly'] is True
        assert morsel['path'] == '/api/auth/'                # only auth endpoints ever receive it
        assert morsel['samesite'] == 'Lax'
        assert int(morsel['max-age']) == THIRTY_DAYS

    def test_register_sets_the_cookie_too(self, api_client):
        r = _register(api_client)
        assert r.status_code == 201 and 'refresh' not in r.data
        assert r.cookies[COOKIE]['httponly'] is True

    def test_changing_the_password_issues_a_fresh_cookie(self, api_client):
        reg = _register(api_client)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {reg.data['token']}")
        old = reg.cookies[COOKIE].value
        r = api_client.post('/api/auth/change-password/', {'current_password': 'Strongpass123!', 'new_password': 'Another456pass!'}, format='json')
        assert r.status_code == 200 and 'refresh' not in r.data
        assert r.cookies[COOKIE].value != old

    def test_the_secure_flag_follows_the_setting(self, api_client, settings):
        # Secure is on in production (HTTPS only); it is off only for local http development.
        settings.AUTH_COOKIE_SECURE = True
        _register(api_client)
        assert _login(api_client).cookies[COOKIE]['secure']


@pytest.mark.django_db
class TestRefreshWithTheCookie:
    def test_refresh_returns_an_access_token_that_works(self, api_client):
        _register(api_client)
        _login(api_client)                                     # the client now holds the cookie
        r = api_client.post(REFRESH, {}, format='json', **CSRF)
        assert r.status_code == 200
        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['token']}")
        assert fresh.get('/api/auth/me/').status_code == 200

    def test_the_cookie_alone_is_not_enough_a_custom_header_is_required(self, api_client):
        _register(api_client)
        _login(api_client)
        assert api_client.post(REFRESH, {}, format='json').status_code == 403   # what a cross-site form post would look like

    def test_no_cookie_and_no_token_is_a_plain_401(self, api_client):
        assert api_client.post(REFRESH, {}, format='json', **CSRF).status_code == 401

    def test_a_garbage_cookie_is_refused_and_cleared(self, api_client):
        api_client.cookies[COOKIE] = 'not-a-token'
        r = api_client.post(REFRESH, {}, format='json', **CSRF)
        assert r.status_code == 401 and int(r.cookies[COOKIE]['max-age']) == 0

    def test_a_password_change_kills_the_old_cookie(self, api_client):
        reg = _register(api_client)
        old_cookie = reg.cookies[COOKIE].value
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {reg.data['token']}")
        api_client.post('/api/auth/change-password/', {'current_password': 'Strongpass123!', 'new_password': 'Another456pass!'}, format='json')
        thief = APIClient()
        thief.cookies[COOKIE] = old_cookie
        r = thief.post(REFRESH, {}, format='json', **CSRF)
        assert r.status_code == 401 and int(r.cookies[COOKIE]['max-age']) == 0

    def test_a_deactivated_account_cannot_refresh(self, api_client):
        _register(api_client)
        _login(api_client)
        User.objects.filter(email='cookie@example.com').update(is_active=False)
        assert api_client.post(REFRESH, {}, format='json', **CSRF).status_code == 401


@pytest.mark.django_db
class TestMigratingOldSessions:
    def _old_style_refresh_token(self):
        user = User.objects.create_user(email='legacy@example.com', name='L', password='Strongpass123!')
        return str(new_refresh_token(user))

    def test_a_localstorage_refresh_token_is_moved_into_the_cookie(self, api_client):
        legacy = self._old_style_refresh_token()
        r = api_client.post(REFRESH, {'refresh': legacy}, format='json')       # no cookie, so no header is needed
        assert r.status_code == 200 and 'token' in r.data
        assert r.cookies[COOKIE]['httponly'] is True and r.cookies[COOKIE].value == legacy

    def test_once_the_cookie_exists_it_is_not_reissued(self, api_client):
        _register(api_client)
        _login(api_client)
        assert COOKIE not in api_client.post(REFRESH, {}, format='json', **CSRF).cookies

    def test_the_body_path_can_be_switched_off(self, api_client, settings):
        settings.AUTH_ALLOW_BODY_REFRESH = False
        assert api_client.post(REFRESH, {'refresh': self._old_style_refresh_token()}, format='json').status_code == 401


@pytest.mark.django_db
class TestLogout:
    def test_logout_clears_the_cookie(self, api_client):
        _register(api_client)
        _login(api_client)
        r = api_client.post('/api/auth/logout/', {}, format='json', **CSRF)
        assert r.status_code == 200 and int(r.cookies[COOKIE]['max-age']) == 0 and r.cookies[COOKIE].value == ''

    def test_a_cross_site_logout_without_the_header_is_refused(self, api_client):
        _register(api_client)
        _login(api_client)
        assert api_client.post('/api/auth/logout/', {}, format='json').status_code == 403

    def test_logging_out_when_already_signed_out_is_fine(self, api_client):
        assert api_client.post('/api/auth/logout/', {}, format='json').status_code == 200
