import pytest
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem


def _make_product(store, **overrides):
    defaults = dict(name='Test Product', cost_price='100.00', selling_price='150.00', quantity=10)
    defaults.update(overrides)
    return Product.objects.create(store=store, **defaults)


@pytest.mark.django_db
class TestTenantIsolation:
    """
    The single most important property of a multi-tenant app: a user with
    access to store A must never be able to read or write store B's data,
    no matter what URL they hit. Every one of these hits a real endpoint
    with a real (but unrelated) store's ID and asserts it's refused.
    """

    def test_unrelated_owner_cannot_list_products(self, other_owner_client, store):
        product = _make_product(store)
        response = other_owner_client.get(f'/api/stores/{store.id}/products/')
        assert response.status_code == 403
        # Belt and braces: even if the status code check above regresses,
        # make sure the other store's product data never actually appears.
        assert str(product.id) not in response.content.decode()

    def test_unrelated_owner_cannot_view_single_product(self, other_owner_client, store):
        product = _make_product(store)
        response = other_owner_client.get(f'/api/stores/{store.id}/products/{product.id}/')
        assert response.status_code == 403

    def test_unrelated_owner_cannot_create_product(self, other_owner_client, store):
        response = other_owner_client.post(f'/api/stores/{store.id}/products/', {
            'name': 'Injected Product', 'cost_price': '10.00', 'selling_price': '20.00', 'quantity': 5,
        }, format='json')
        assert response.status_code == 403
        assert not Product.objects.filter(store=store, name='Injected Product').exists()

    def test_unrelated_owner_cannot_delete_product(self, other_owner_client, store):
        product = _make_product(store)
        response = other_owner_client.delete(f'/api/stores/{store.id}/products/{product.id}/')
        assert response.status_code == 403
        assert Product.objects.filter(id=product.id).exists()

    def test_unrelated_owner_cannot_view_sales(self, other_owner_client, store, owner_user):
        product = _make_product(store)
        sale = Sale.objects.create(store=store, recorded_by=owner_user, total_amount=150, total_profit=50)
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=150, unit_cost=100, profit=50)

        response = other_owner_client.get(f'/api/stores/{store.id}/sales/')
        assert response.status_code == 403

    def test_unrelated_owner_cannot_delete_sale(self, other_owner_client, store, owner_user):
        product = _make_product(store)
        sale = Sale.objects.create(store=store, recorded_by=owner_user, total_amount=150, total_profit=50)
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=150, unit_cost=100, profit=50)

        response = other_owner_client.delete(f'/api/stores/{store.id}/sales/{sale.id}/')
        assert response.status_code == 403
        assert Sale.objects.filter(id=sale.id).exists()

    def test_unrelated_owner_cannot_view_dashboard(self, other_owner_client, store):
        response = other_owner_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.status_code == 403

    def test_cashier_cannot_access_a_different_store_they_have_no_role_in(self, cashier_client, other_store):
        # cashier_client only has a Staff role on `store`, none at all on `other_store`.
        response = cashier_client.get(f'/api/stores/{other_store.id}/products/')
        assert response.status_code == 403

    def test_nonexistent_store_returns_404_not_500(self, owner_client):
        response = owner_client.get('/api/stores/00000000-0000-0000-0000-000000000000/products/')
        assert response.status_code == 404


@pytest.mark.django_db
class TestRolePermissions:
    def test_cashier_cannot_view_dashboard(self, cashier_client, store):
        response = cashier_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.status_code == 403

    def test_cashier_can_view_products(self, cashier_client, store):
        _make_product(store)
        response = cashier_client.get(f'/api/stores/{store.id}/products/')
        assert response.status_code == 200

    def test_cashier_cannot_delete_product(self, cashier_client, store):
        product = _make_product(store)
        response = cashier_client.delete(f'/api/stores/{store.id}/products/{product.id}/')
        assert response.status_code == 403

    def test_manager_can_view_dashboard(self, manager_client, store):
        response = manager_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.status_code == 200

    def test_owner_can_view_dashboard(self, owner_client, store):
        response = owner_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.status_code == 200


@pytest.mark.django_db
class TestStaffManagement:
    def test_owner_cannot_add_self_as_staff(self, owner_client, store, owner_user):
        response = owner_client.post(f'/api/stores/{store.id}/staff/', {
            'email': owner_user.email, 'role': 'MANAGER',
        }, format='json')
        assert response.status_code == 400
        from apps.stores.models import Staff
        assert not Staff.objects.filter(store=store, user=owner_user).exists()

    def test_owner_can_add_a_different_user_as_staff(self, owner_client, store, cashier_user):
        response = owner_client.post(f'/api/stores/{store.id}/staff/', {
            'email': cashier_user.email, 'role': 'CASHIER',
        }, format='json')
        assert response.status_code == 201
        from apps.stores.models import Staff
        assert Staff.objects.filter(store=store, user=cashier_user, role='CASHIER').exists()

    def test_cashier_cannot_add_staff(self, cashier_client, store, manager_user):
        response = cashier_client.post(f'/api/stores/{store.id}/staff/', {
            'email': manager_user.email, 'role': 'MANAGER',
        }, format='json')
        assert response.status_code == 403
