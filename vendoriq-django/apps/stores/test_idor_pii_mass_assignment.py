"""
Regression tests for three classes of weakness:
  * IDOR  - using an id that belongs to ANOTHER store (in the URL or in the request body)
  * mass assignment - sending fields a client must never be able to set
  * personal data  - what one person can learn about another
"""
import pytest

from apps.authentication.models import User
from apps.customers.models import Customer
from apps.products.models import Product
from apps.sales.models import Sale
from apps.stores.models import Staff


def _product(store, **kw):
    d = dict(name='Widget', cost_price='100.00', selling_price='150.00', quantity=10)
    d.update(kw)
    return Product.objects.create(store=store, **d)


@pytest.mark.django_db
class TestIdorThroughTheBody:
    """Ids inside a request must belong to the store in the URL, not just exist."""

    def test_cannot_sell_another_stores_product(self, owner_client, store, other_store):
        theirs = _product(other_store)
        r = owner_client.post(f'/api/stores/{store.id}/sales/', {'items': [{'productId': str(theirs.id), 'quantity': 1}]}, format='json')
        assert r.status_code in (400, 404)
        theirs.refresh_from_db()
        assert theirs.quantity == 10                       # their stock untouched
        assert Sale.objects.filter(store=store).count() == 0

    def test_cannot_attach_another_stores_customer_to_a_sale(self, owner_client, store, other_store):
        mine = _product(store)
        stranger = Customer.objects.create(store=other_store, name='Not My Customer', phone='08099990000')
        r = owner_client.post(f'/api/stores/{store.id}/sales/',
                              {'items': [{'productId': str(mine.id), 'quantity': 1}], 'customerId': str(stranger.id)}, format='json')
        assert r.status_code in (400, 404, 403)
        assert Sale.objects.filter(store=store).count() == 0

    def test_cannot_return_against_another_stores_sale_through_my_store_url(self, owner_client, other_owner_client, store, other_store, owner_user):
        theirs = _product(other_store)
        sale = other_owner_client.post(f'/api/stores/{other_store.id}/sales/', {'items': [{'productId': str(theirs.id), 'quantity': 2}]}, format='json').json()['sale']
        r = owner_client.post(f'/api/stores/{store.id}/sales/{sale["id"]}/returns/', {'items': [{'productId': str(theirs.id), 'quantity': 1}]}, format='json')
        assert r.status_code == 404
        theirs.refresh_from_db()
        assert theirs.quantity == 8

    def test_cannot_read_or_delete_another_stores_customer_through_my_store_url(self, owner_client, store, other_store):
        stranger = Customer.objects.create(store=other_store, name='Hidden', phone='08011110000')
        assert owner_client.get(f'/api/stores/{store.id}/customers/{stranger.id}/statement/').status_code == 404
        assert owner_client.delete(f'/api/stores/{store.id}/customers/{stranger.id}/').status_code == 404
        assert Customer.objects.filter(pk=stranger.pk).exists()

    def test_cannot_touch_another_stores_staff_row_through_my_store_url(self, owner_client, store, other_store, cashier_user):
        row = Staff.objects.create(store=other_store, user=cashier_user, role='CASHIER')
        assert owner_client.patch(f'/api/stores/{store.id}/staff/{row.id}/', {'role': 'MANAGER'}, format='json').status_code == 404
        assert owner_client.delete(f'/api/stores/{store.id}/staff/{row.id}/').status_code == 404
        row.refresh_from_db()
        assert row.role == 'CASHIER'


@pytest.mark.django_db
class TestMassAssignment:
    def test_register_cannot_create_an_admin(self, api_client):
        r = api_client.post('/api/auth/register/', {
            'name': 'Eve', 'email': 'eve@example.com', 'phone': '08037770001', 'password': 'Strongpass123!',
            'is_staff': True, 'is_superuser': True, 'email_verified': True, 'phone_verified': True,
        }, format='json')
        assert r.status_code == 201
        eve = User.objects.get(email='eve@example.com')
        assert not eve.is_staff and not eve.is_superuser
        assert not eve.email_verified and not eve.phone_verified

    def test_profile_update_cannot_change_flags_or_email(self, owner_client, owner_user):
        email = owner_user.email
        owner_client.patch('/api/auth/me/', {'name': 'New Name', 'email': 'hijack@example.com', 'is_staff': True, 'email_verified': True,
                                             'phone_verified': True, 'referral_code': '08000000000'}, format='json')
        owner_user.refresh_from_db()
        assert owner_user.name == 'New Name'
        assert owner_user.email == email and not owner_user.is_staff
        assert not owner_user.email_verified and owner_user.referral_code != '08000000000'

    def test_product_create_cannot_choose_the_store(self, owner_client, store, other_store):
        r = owner_client.post(f'/api/stores/{store.id}/products/', {
            'name': 'Sneaky', 'cost_price': '1.00', 'selling_price': '2.00', 'quantity': 1, 'store': str(other_store.id)}, format='json')
        assert r.status_code == 201
        assert Product.objects.get(name='Sneaky').store_id == store.id

    def test_store_update_cannot_change_the_owner(self, owner_client, store, other_owner_user):
        owner_client.patch(f'/api/stores/{store.id}/', {'name': 'Renamed', 'owner': str(other_owner_user.id), 'owner_id': str(other_owner_user.id)}, format='json')
        store.refresh_from_db()
        assert store.name == 'Renamed' and store.owner_id != other_owner_user.id

    def test_a_manager_cannot_grant_owner_through_staff(self, manager_client, store, cashier_user):
        r = manager_client.post(f'/api/stores/{store.id}/staff/', {'email': cashier_user.email, 'role': 'OWNER'}, format='json')
        assert r.status_code == 400


@pytest.mark.django_db
class TestPersonalData:
    def test_adding_staff_does_not_reveal_their_phone_or_referral_code(self, owner_client, store, cashier_user):
        cashier_user.phone, cashier_user.phone_verified = '08031234567', True
        cashier_user.save()
        r = owner_client.post(f'/api/stores/{store.id}/staff/', {'email': cashier_user.email, 'role': 'CASHIER'}, format='json')
        assert r.status_code == 201
        user = r.json()['staff']['user']
        assert set(user) == {'id', 'name', 'email'}
        assert '08031234567' not in r.content.decode()

    def test_the_staff_list_does_not_reveal_phone_numbers(self, owner_client, store, cashier_staff, cashier_user):
        cashier_user.phone = '08031234567'
        cashier_user.save()
        body = owner_client.get(f'/api/stores/{store.id}/staff/').content.decode()
        assert '08031234567' not in body and 'referral_code' not in body

    def test_the_referral_summary_masks_the_referred_persons_email(self, owner_client, owner_user, other_owner_user):
        from apps.referrals.models import Referral
        Referral.objects.create(referrer=owner_user, referred_user=other_owner_user, code_used=owner_user.referral_code or '08000000001')
        body = owner_client.get('/api/referrals/summary/')
        assert body.status_code == 200
        assert other_owner_user.email not in body.content.decode()
        assert body.json()['referredUsers'][0]['email'].startswith(other_owner_user.email[0] + '***@')

    def test_a_cashier_never_receives_cost_or_profit(self, cashier_client, store, cashier_staff):
        _product(store)
        assert 'cost_price' not in cashier_client.get(f'/api/stores/{store.id}/products/').content.decode()
        assert 'cost_price' not in cashier_client.get(f'/api/stores/{store.id}/catalog/').content.decode()
