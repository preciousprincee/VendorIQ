import pytest
from apps.products.models import Product
from apps.sales.models import Sale


def _make_product(store, **overrides):
    defaults = dict(name='Test Product', cost_price='100.00', selling_price='150.00', quantity=10)
    defaults.update(overrides)
    return Product.objects.create(store=store, **defaults)


@pytest.mark.django_db
class TestRecordSale:
    def test_recording_a_sale_deducts_stock(self, owner_client, store):
        product = _make_product(store, quantity=10)
        response = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 3}],
        }, format='json')
        assert response.status_code == 201
        product.refresh_from_db()
        assert product.quantity == 7

    def test_sale_records_correct_revenue_and_profit(self, owner_client, store):
        product = _make_product(store, cost_price='100.00', selling_price='150.00', quantity=10)
        response = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 2}],
        }, format='json')
        assert response.status_code == 201
        sale = Sale.objects.get(id=response.data['sale']['id'])
        assert float(sale.total_amount) == 300.0  # 150 * 2
        assert float(sale.total_profit) == 100.0  # (150-100) * 2

    def test_cannot_sell_more_than_available_stock(self, owner_client, store):
        product = _make_product(store, quantity=2)
        response = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 5}],
        }, format='json')
        assert response.status_code == 400
        product.refresh_from_db()
        assert product.quantity == 2  # unchanged - the whole sale should have been rejected, not partially applied

    def test_cashier_can_record_a_sale(self, cashier_client, store):
        product = _make_product(store, quantity=10)
        response = cashier_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 1}],
        }, format='json')
        assert response.status_code == 201


@pytest.mark.django_db
class TestDeleteSale:
    def test_deleting_a_sale_restores_stock(self, owner_client, store, owner_user):
        product = _make_product(store, quantity=10)
        create_resp = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 4}],
        }, format='json')
        sale_id = create_resp.data['sale']['id']
        product.refresh_from_db()
        assert product.quantity == 6

        delete_resp = owner_client.delete(f'/api/stores/{store.id}/sales/{sale_id}/')
        assert delete_resp.status_code == 200
        product.refresh_from_db()
        assert product.quantity == 10
        assert not Sale.objects.filter(id=sale_id).exists()

    def test_cashier_can_delete_their_own_sale(self, cashier_client, store):
        product = _make_product(store, quantity=10)
        create_resp = cashier_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 1}],
        }, format='json')
        sale_id = create_resp.data['sale']['id']

        delete_resp = cashier_client.delete(f'/api/stores/{store.id}/sales/{sale_id}/')
        assert delete_resp.status_code == 200

    def test_cashier_cannot_delete_someone_elses_sale(self, owner_client, cashier_client, store):
        product = _make_product(store, quantity=10)
        # Owner records the sale, not the cashier.
        create_resp = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 1}],
        }, format='json')
        sale_id = create_resp.data['sale']['id']

        delete_resp = cashier_client.delete(f'/api/stores/{store.id}/sales/{sale_id}/')
        assert delete_resp.status_code == 403
        assert Sale.objects.filter(id=sale_id).exists()

    def test_manager_can_delete_any_sale(self, owner_client, manager_client, store):
        product = _make_product(store, quantity=10)
        create_resp = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(product.id), 'quantity': 1}],
        }, format='json')
        sale_id = create_resp.data['sale']['id']

        delete_resp = manager_client.delete(f'/api/stores/{store.id}/sales/{sale_id}/')
        assert delete_resp.status_code == 200
