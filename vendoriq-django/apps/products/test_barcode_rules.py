"""A barcode identifies ONE product in a store, otherwise a scan at the till rings up the wrong item."""
import pytest

from apps.products.models import Product


def _make(store, name, barcode):
    return Product.objects.create(store=store, name=name, barcode=barcode, cost_price='1.00', selling_price='2.00', quantity=5)


@pytest.mark.django_db
class TestBarcodeUniqueness:
    def test_a_second_product_cannot_reuse_a_barcode(self, owner_client, store):
        _make(store, 'Indomie', '6001234567890')
        r = owner_client.post(f'/api/stores/{store.id}/products/', {'name': 'Other', 'barcode': '6001234567890', 'cost_price': '1', 'selling_price': '2', 'quantity': 1}, format='json')
        assert r.status_code == 400 and 'Indomie' in r.json()['error']

    def test_surrounding_spaces_do_not_hide_a_duplicate(self, owner_client, store):
        _make(store, 'Indomie', '6001234567890')
        r = owner_client.post(f'/api/stores/{store.id}/products/', {'name': 'Other', 'barcode': ' 6001234567890 ', 'cost_price': '1', 'selling_price': '2', 'quantity': 1}, format='json')
        assert r.status_code == 400

    def test_the_same_barcode_is_fine_in_another_store(self, owner_client, store, other_store):
        _make(other_store, 'Theirs', '6001234567890')
        r = owner_client.post(f'/api/stores/{store.id}/products/', {'name': 'Mine', 'barcode': '6001234567890', 'cost_price': '1', 'selling_price': '2', 'quantity': 1}, format='json')
        assert r.status_code == 201

    def test_blank_barcodes_are_stored_as_none_and_never_clash(self, owner_client, store):
        for name in ('A', 'B'):
            r = owner_client.post(f'/api/stores/{store.id}/products/', {'name': name, 'barcode': '   ', 'cost_price': '1', 'selling_price': '2', 'quantity': 1}, format='json')
            assert r.status_code == 201
        assert Product.objects.filter(store=store, barcode__isnull=True).count() == 2

    def test_editing_a_product_with_an_existing_duplicate_is_not_blocked(self, owner_client, store):
        a, b = _make(store, 'A', '111'), _make(store, 'B', '111')      # legacy data: two products share a barcode
        r = owner_client.patch(f'/api/stores/{store.id}/products/{b.id}/', {'barcode': '111', 'name': 'B renamed'}, format='json')
        assert r.status_code == 200

    def test_changing_to_someone_elses_barcode_is_refused(self, owner_client, store):
        _make(store, 'A', '111')
        b = _make(store, 'B', '222')
        r = owner_client.patch(f'/api/stores/{store.id}/products/{b.id}/', {'barcode': '111'}, format='json')
        assert r.status_code == 400
