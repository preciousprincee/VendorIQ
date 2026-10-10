import pytest
from apps.products.models import Product


def _product(store, **kw):
    d = dict(name='P', cost_price='100.00', selling_price='150.00', quantity=10)
    d.update(kw)
    return Product.objects.create(store=store, **d)


@pytest.mark.django_db
class TestMultiItemSaleIsAllOrNothing:
    def test_second_item_out_of_stock_leaves_first_items_stock_untouched(self, owner_client, store):
        a = _product(store, name='A', quantity=10)
        b = _product(store, name='B', quantity=1)
        response = owner_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(a.id), 'quantity': 3}, {'productId': str(b.id), 'quantity': 5}],
        }, format='json')
        assert response.status_code == 400
        a.refresh_from_db()
        assert a.quantity == 10  # used to stay at 7 with no sale recorded


@pytest.mark.django_db
class TestCashierCannotSeeCostsOrReprice:
    def test_product_list_hides_cost_price(self, cashier_client, store):
        _product(store)
        response = cashier_client.get(f'/api/stores/{store.id}/products/')
        assert response.status_code == 200
        for p in response.data['products']:
            assert 'cost_price' not in p and 'costPrice' not in p

    def test_sale_response_hides_profit(self, cashier_client, store):
        p = _product(store)
        response = cashier_client.post(f'/api/stores/{store.id}/sales/', {
            'items': [{'productId': str(p.id), 'quantity': 1}],
        }, format='json')
        assert response.status_code == 201
        sale = response.data['sale']
        assert 'total_profit' not in sale and 'totalProfit' not in sale
        for item in sale.get('items', sale.get('sale_items', [])):
            assert 'unit_cost' not in item and 'profit' not in item

    def test_cashier_cannot_change_prices(self, cashier_client, store):
        p = _product(store)
        response = cashier_client.patch(f'/api/stores/{store.id}/products/{p.id}/', {'selling_price': '1.00'}, format='json')
        assert response.status_code == 403
        p.refresh_from_db()
        assert str(p.selling_price) == '150.00'


@pytest.mark.django_db
class TestBadInputIsA400NotA500:
    def test_trend_with_non_numeric_days(self, owner_client, store):
        assert owner_client.get(f'/api/stores/{store.id}/insights/trend/?days=abc').status_code == 400

    def test_expenses_with_malformed_dates(self, owner_client, store):
        assert owner_client.get(f'/api/stores/{store.id}/expenses/?start=not-a-date').status_code == 400

    def test_duplicate_barcode_lookup_does_not_crash(self, owner_client, store):
        _product(store, name='A', barcode='123')
        _product(store, name='B', barcode='123')
        response = owner_client.get(f'/api/stores/{store.id}/products/barcode/?barcode=123')
        assert response.status_code == 200

    def test_restock_rejects_boolean(self, owner_client, store):
        p = _product(store)
        response = owner_client.patch(f'/api/stores/{store.id}/products/{p.id}/restock/', {'quantity': True}, format='json')
        assert response.status_code == 400
