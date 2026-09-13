import pytest
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.stores.models import Store, Staff


@pytest.fixture
def api_client():
    return APIClient()


def _make_user(email, name='Test User', password='Testpass123!'):
    user = User.objects.create_user(email=email, name=name, password=password)
    return user


@pytest.fixture
def owner_user(db):
    return _make_user('owner@example.com', 'Store Owner')


@pytest.fixture
def other_owner_user(db):
    """A second, unrelated owner - used for tenant-isolation tests."""
    return _make_user('otherowner@example.com', 'Other Owner')


@pytest.fixture
def cashier_user(db):
    return _make_user('cashier@example.com', 'Cashier Person')


@pytest.fixture
def manager_user(db):
    return _make_user('manager@example.com', 'Manager Person')


@pytest.fixture
def store(db, owner_user):
    return Store.objects.create(name='Test Store', location='Lagos', owner=owner_user)


@pytest.fixture
def other_store(db, other_owner_user):
    """A second, unrelated store owned by a different user - for tenant isolation tests."""
    return Store.objects.create(name='Someone Else\'s Store', location='Abuja', owner=other_owner_user)


@pytest.fixture
def cashier_staff(db, store, cashier_user):
    return Staff.objects.create(store=store, user=cashier_user, role='CASHIER')


@pytest.fixture
def manager_staff(db, store, manager_user):
    return Staff.objects.create(store=store, user=manager_user, role='MANAGER')


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def owner_client(owner_user):
    return _auth_client(owner_user)


@pytest.fixture
def other_owner_client(other_owner_user):
    return _auth_client(other_owner_user)


@pytest.fixture
def cashier_client(cashier_user, cashier_staff):
    return _auth_client(cashier_user)


@pytest.fixture
def manager_client(manager_user, manager_staff):
    return _auth_client(manager_user)
