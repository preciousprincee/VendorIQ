"""
POS behaviour: payments, discounts, credit, returns, debt payments, shifts,
offline sync, catalog, reports, backup. Money numbers are worked out by hand
in the comments - if one fails, the arithmetic is what to read first.
Fixture prices: cost 100, selling 150.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.billing.plans import ANNUAL
from apps.billing.services import create_subscription_purchase
from apps.customers.models import Customer
from apps.products.models import Product
from apps.sales.models import Sale, Shift


def D(x):
    return Decimal(str(x))


def _product(store, **kw):
    d = dict(name='Widget', cost_price='100.00', selling_price='150.00', quantity=10)
    d.update(kw)
    return Product.objects.create(store=store, **d)


def _sell(client, store, product, qty=1, **extra):
    body = {'items': [{'productId': str(product.id), 'quantity': qty}], **extra}
    return client.post(f'/api/stores/{store.id}/sales/', body, format='json')


@pytest.fixture
def pro(owner_user):
    create_subscription_purchase(
        user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=4800000, currency='NGN',
        payment_provider='paystack', payment_reference='ref-pos-pro',
    )


@pytest.fixture
def customer(store, pro):
    return Customer.objects.create(store=store, name='Mama Chidi', phone='08011112222')


@pytest.mark.django_db
class TestPayments:
    def test_no_payments_key_means_paid_in_full_in_cash(self, owner_client, store):
        r = _sell(owner_client, store, _product(store), 2)
        assert r.status_code == 201
        sale = r.data['sale']
        assert D(sale['total_amount']) == 300 and D(sale['amount_paid']) == 300
        assert sale['payment_status'] == 'PAID' and sale['payments'][0]['method'] == 'CASH'

    def test_split_payment_cash_and_transfer(self, owner_client, store):
        r = _sell(owner_client, store, _product(store), 2, payments=[
            {'method': 'CASH', 'amount': '100'}, {'method': 'TRANSFER', 'amount': '200'}])
        assert r.status_code == 201
        methods = {p['method']: D(p['amount']) for p in r.data['sale']['payments']}
        assert methods == {'CASH': 100, 'TRANSFER': 200}
        assert r.data['sale']['payment_status'] == 'PAID'

    def test_cash_overpayment_produces_change(self, owner_client, store):
        r = _sell(owner_client, store, _product(store), 2, payments=[{'method': 'CASH', 'amount': '500'}])
        sale = r.data['sale']
        assert D(sale['cash_tendered']) == 500 and D(sale['change_given']) == 200
        assert D(sale['amount_paid']) == 300  # change is not revenue

    def test_card_or_transfer_cannot_be_overpaid(self, owner_client, store):
        p = _product(store)
        r = _sell(owner_client, store, p, 2, payments=[{'method': 'TRANSFER', 'amount': '400'}])
        assert r.status_code == 400
        p.refresh_from_db()
        assert p.quantity == 10

    def test_unpaid_balance_without_a_customer_is_refused_and_stock_untouched(self, owner_client, store):
        p = _product(store)
        r = _sell(owner_client, store, p, 2, payments=[{'method': 'CASH', 'amount': '100'}])
        assert r.status_code == 400 and 'customer' in r.data['error'].lower()
        p.refresh_from_db()
        assert p.quantity == 10

    def test_credit_sale_with_a_customer(self, owner_client, store, customer):
        r = _sell(owner_client, store, _product(store), 2, customerId=str(customer.id),
                  payments=[{'method': 'CASH', 'amount': '100'}])
        assert r.status_code == 201
        sale = r.data['sale']
        assert D(sale['credit_amount']) == 200 and D(sale['balance_due']) == 200
        assert sale['payment_status'] == 'PARTIAL'

    def test_customers_are_a_pro_feature(self, owner_client, store):
        c = Customer.objects.create(store=store, name='X')
        r = _sell(owner_client, store, _product(store), 1, customerId=str(c.id))
        assert r.status_code == 402


@pytest.mark.django_db
class TestDiscounts:
    def test_percent_discount_reduces_total_and_profit(self, owner_client, store):
        # 2 x 150 = 300, 10% off = 30 -> total 270; cost 200 -> profit 70
        r = _sell(owner_client, store, _product(store), 2, discount={'type': 'PERCENT', 'value': '10'})
        sale = r.data['sale']
        assert D(sale['subtotal']) == 300 and D(sale['discount_amount']) == 30
        assert D(sale['total_amount']) == 270 and D(sale['total_profit']) == 70

    def test_amount_discount(self, owner_client, store):
        r = _sell(owner_client, store, _product(store), 2, discount={'type': 'AMOUNT', 'value': '50'})
        assert D(r.data['sale']['total_amount']) == 250

    def test_discount_bigger_than_the_sale_is_refused(self, owner_client, store):
        assert _sell(owner_client, store, _product(store), 1, discount={'type': 'AMOUNT', 'value': '999'}).status_code == 400
        assert _sell(owner_client, store, _product(store), 1, discount={'type': 'PERCENT', 'value': '101'}).status_code == 400

    def test_cashier_is_capped_but_manager_is_not(self, cashier_client, manager_client, store):
        p = _product(store)
        too_much = _sell(cashier_client, store, p, 2, discount={'type': 'PERCENT', 'value': '20'})
        assert too_much.status_code == 403
        p.refresh_from_db()
        assert p.quantity == 10
        assert _sell(cashier_client, store, p, 2, discount={'type': 'PERCENT', 'value': '10'}).status_code == 201
        assert _sell(manager_client, store, p, 2, discount={'type': 'PERCENT', 'value': '20'}).status_code == 201


@pytest.mark.django_db
class TestIdempotency:
    def test_same_client_id_is_recorded_once(self, owner_client, store):
        p = _product(store)
        cid = str(uuid.uuid4())
        first = _sell(owner_client, store, p, 3, clientId=cid)
        again = _sell(owner_client, store, p, 3, clientId=cid)
        assert first.status_code == 201 and again.status_code == 200 and again.data['duplicate'] is True
        assert Sale.objects.filter(store=store).count() == 1
        p.refresh_from_db()
        assert p.quantity == 7  # deducted once, not twice


@pytest.mark.django_db
class TestReturns:
    def _return(self, client, store, sale, qty, **kw):
        item = sale['sale_items'][0]
        return client.post(f"/api/stores/{store.id}/sales/{sale['id']}/returns/",
                           {'items': [{'saleItemId': item['id'], 'quantity': qty}], **kw}, format='json')

    def test_partial_return_refunds_restocks_and_nets_the_sale(self, owner_client, store):
        p = _product(store)
        sale = _sell(owner_client, store, p, 3).data['sale']  # 450 paid in cash
        r = self._return(owner_client, store, sale, 1, refundMethod='CASH')
        assert r.status_code == 201 and r.data['refundAmount'] == 150
        s = r.data['sale']
        assert D(s['total_amount']) == 300 and D(s['returned_amount']) == 150
        assert D(s['total_profit']) == 100  # 300 - cost of the 2 units kept (200)
        p.refresh_from_db()
        assert p.quantity == 8  # 10 - 3 + 1

    def test_refund_needs_a_method_when_money_goes_back(self, owner_client, store):
        sale = _sell(owner_client, store, _product(store), 2).data['sale']
        assert self._return(owner_client, store, sale, 1).status_code == 400

    def test_cannot_return_more_than_was_sold(self, owner_client, store):
        sale = _sell(owner_client, store, _product(store), 2).data['sale']
        assert self._return(owner_client, store, sale, 3, refundMethod='CASH').status_code == 400
        assert self._return(owner_client, store, sale, 2, refundMethod='CASH').status_code == 201
        assert self._return(owner_client, store, sale, 1, refundMethod='CASH').status_code == 400

    def test_discount_is_shared_across_returned_lines_and_a_full_return_lands_on_zero(self, owner_client, store):
        # 300 less 10% = 270. One unit back = 150 * (1 - 30/300) = 135; the rest = 135.
        sale = _sell(owner_client, store, _product(store), 2, discount={'type': 'PERCENT', 'value': '10'}).data['sale']
        first = self._return(owner_client, store, sale, 1, refundMethod='CASH')
        assert first.data['refundAmount'] == 135 and D(first.data['sale']['total_amount']) == 135
        second = self._return(owner_client, store, sale, 1, refundMethod='CASH')
        assert second.data['refundAmount'] == 135
        end = second.data['sale']
        assert D(end['total_amount']) == 0 and D(end['total_profit']) == 0 and D(end['balance_due']) == 0

    def test_returning_goods_from_a_credit_sale_reduces_the_debt_not_cash(self, owner_client, store, customer):
        sale = _sell(owner_client, store, _product(store), 2, customerId=str(customer.id), payments=[]).data['sale']
        assert D(sale['balance_due']) == 300
        r = self._return(owner_client, store, sale, 1)  # nothing was paid, so nothing to refund
        assert r.status_code == 201 and r.data['refundAmount'] == 0
        assert D(r.data['sale']['balance_due']) == 150

    def test_a_cashier_cannot_process_returns(self, owner_client, cashier_client, store):
        sale = _sell(owner_client, store, _product(store), 2).data['sale']
        assert self._return(cashier_client, store, sale, 1, refundMethod='CASH').status_code == 403

    def test_sale_with_returns_cannot_be_deleted(self, owner_client, store):
        sale = _sell(owner_client, store, _product(store), 2).data['sale']
        self._return(owner_client, store, sale, 1, refundMethod='CASH')
        assert owner_client.delete(f"/api/stores/{store.id}/sales/{sale['id']}/").status_code == 400

    def test_returned_units_leave_the_best_seller_count(self, owner_client, store):
        from django.db.models import F, Sum
        from apps.sales.models import SaleItem
        sale = _sell(owner_client, store, _product(store), 3).data['sale']
        self._return(owner_client, store, sale, 2, refundMethod='CASH')
        net = SaleItem.objects.filter(sale__store=store).aggregate(n=Sum(F('quantity') - F('returned_quantity')))['n']
        assert net == 1


@pytest.mark.django_db
class TestCustomerDebt:
    def _credit(self, client, store, product, customer, qty):
        return _sell(client, store, product, qty, customerId=str(customer.id), payments=[]).data['sale']

    def _pay(self, client, store, customer, amount, **kw):
        return client.post(f'/api/stores/{store.id}/customers/{customer.id}/payments/',
                           {'amount': amount, 'method': 'CASH', **kw}, format='json')

    def test_payment_clears_the_oldest_sale_first(self, owner_client, store, customer):
        p = _product(store, quantity=50)
        first = self._credit(owner_client, store, p, customer, 2)   # 300
        second = self._credit(owner_client, store, p, customer, 3)  # 450
        r = self._pay(owner_client, store, customer, 400)
        assert r.status_code == 201 and r.data['customer']['balance'] == 350
        assert D(Sale.objects.get(id=first['id']).balance_due) == 0
        assert D(Sale.objects.get(id=second['id']).balance_due) == 350

    def test_cannot_pay_more_than_is_owed_and_retries_do_not_double_apply(self, owner_client, store, customer):
        p = _product(store)
        self._credit(owner_client, store, p, customer, 2)  # owes 300
        assert self._pay(owner_client, store, customer, 400).status_code == 400
        cid = str(uuid.uuid4())
        assert self._pay(owner_client, store, customer, 100, clientId=cid).status_code == 201
        again = self._pay(owner_client, store, customer, 100, clientId=cid)
        assert again.status_code == 200 and again.data['duplicate'] is True
        assert again.data['customer']['balance'] == 200  # applied once

    def test_customers_belong_to_one_store(self, owner_client, store, customer, other_owner_user):
        from apps.stores.models import Store
        other_store = Store.objects.create(owner=other_owner_user, name='Other')
        r = owner_client.post(f'/api/stores/{other_store.id}/customers/{customer.id}/payments/',
                              {'amount': 10, 'method': 'CASH'}, format='json')
        assert r.status_code in (403, 404)


@pytest.mark.django_db
class TestShifts:
    def test_till_count_and_variance(self, owner_client, store):
        base = f'/api/stores/{store.id}/shifts/'
        assert owner_client.post(base + 'open/', {'openingFloat': 1000}, format='json').status_code == 201
        assert owner_client.post(base + 'open/', {'openingFloat': 0}, format='json').status_code == 400  # one open shift only

        p = _product(store, quantity=50)
        cash_sale = _sell(owner_client, store, p, 2).data['sale']                                   # +300 cash
        _sell(owner_client, store, p, 2, payments=[{'method': 'TRANSFER', 'amount': '300'}])       # not cash
        owner_client.post(f"/api/stores/{store.id}/sales/{cash_sale['id']}/returns/", {
            'items': [{'saleItemId': cash_sale['sale_items'][0]['id'], 'quantity': 1}], 'refundMethod': 'CASH'}, format='json')  # -150

        current = owner_client.get(base + 'current/').data
        assert current['shift']['live_expected_cash'] == 1150  # 1000 + 300 - 150
        shift_id = current['shift']['id']

        closed = owner_client.post(base + f'{shift_id}/close/', {'countedCash': 1100}, format='json')
        assert closed.status_code == 200
        s = closed.data['shift']
        assert D(s['expected_cash']) == 1150 and D(s['counted_cash']) == 1100 and D(s['variance']) == -50
        assert closed.data['summary']['received_by_method']['TRANSFER'] == 300
        assert owner_client.post(base + f'{shift_id}/close/', {'countedCash': 1100}, format='json').status_code == 400

    def test_sale_in_a_closed_shift_cannot_be_deleted(self, owner_client, store):
        base = f'/api/stores/{store.id}/shifts/'
        owner_client.post(base + 'open/', {'openingFloat': 0}, format='json')
        sale = _sell(owner_client, store, _product(store), 1).data['sale']
        owner_client.post(base + f"{owner_client.get(base + 'current/').data['shift']['id']}/close/", {'countedCash': 150}, format='json')
        assert owner_client.delete(f"/api/stores/{store.id}/sales/{sale['id']}/").status_code == 400

    def test_a_cashier_cannot_see_someone_elses_shift(self, owner_client, cashier_client, store):
        owner_client.post(f'/api/stores/{store.id}/shifts/open/', {'openingFloat': 0}, format='json')
        sid = owner_client.get(f'/api/stores/{store.id}/shifts/current/').data['shift']['id']
        assert cashier_client.get(f'/api/stores/{store.id}/shifts/{sid}/').status_code == 404
        assert cashier_client.get(f'/api/stores/{store.id}/shifts/').data['shifts'] == []

    def test_bad_amounts_are_a_400_not_a_500(self, owner_client, store):
        base = f'/api/stores/{store.id}/shifts/'
        assert owner_client.post(base + 'open/', {'openingFloat': 'abc'}, format='json').status_code == 400
        assert owner_client.post(base + 'open/', {'openingFloat': -5}, format='json').status_code == 400


def _op(kind, payload, created_at=None, client_id=None):
    return {'type': kind, 'clientId': client_id or str(uuid.uuid4()), 'createdAt': created_at, 'payload': payload}


def _sync(client, store, *ops):
    return client.post(f'/api/stores/{store.id}/sync/', {'operations': list(ops)}, format='json')


@pytest.mark.django_db
class TestOfflineSync:
    def test_replay_is_idempotent(self, owner_client, store):
        p = _product(store)
        op = _op('sale', {'items': [{'productId': str(p.id), 'quantity': 2}]})
        first = _sync(owner_client, store, op).data['results'][0]
        again = _sync(owner_client, store, op).data['results'][0]
        assert first['status'] == 'synced' and again['status'] == 'duplicate'
        assert Sale.objects.filter(store=store).count() == 1
        p.refresh_from_db()
        assert p.quantity == 8

    def test_goods_that_already_left_are_recorded_and_flagged_not_refused(self, owner_client, store):
        p = _product(store, quantity=2)
        r = _sync(owner_client, store, _op('sale', {'items': [{'productId': str(p.id), 'quantity': 5}]})).data['results'][0]
        assert r['status'] == 'synced'
        sale = Sale.objects.get(store=store)
        assert sale.needs_review and 'only 2' in sale.review_notes
        p.refresh_from_db()
        assert p.quantity == 0  # clamped, never negative

    def test_the_price_the_customer_was_charged_is_honoured_and_flagged(self, owner_client, store):
        p = _product(store)  # now 150
        _sync(owner_client, store, _op('sale', {'items': [{'productId': str(p.id), 'quantity': 2, 'unitPrice': '120.00'}]}))
        sale = Sale.objects.get(store=store)
        assert sale.total_amount == 240 and sale.needs_review and '120' in sale.review_notes

    def test_one_bad_operation_does_not_block_the_rest(self, owner_client, store):
        good = _product(store)
        bad_op = _op('sale', {'items': [{'productId': str(uuid.uuid4()), 'quantity': 1}]})
        good_op = _op('sale', {'items': [{'productId': str(good.id), 'quantity': 1}]})
        results = _sync(owner_client, store, bad_op, good_op).data['results']
        assert [r['status'] for r in results] == ['rejected', 'synced']
        assert 'no longer exists' in results[0]['error']

    def test_sale_keeps_the_time_it_happened_within_a_sane_window(self, owner_client, store):
        p = _product(store, quantity=50)
        three_days = (timezone.now() - timedelta(days=3)).isoformat()
        thirty_days = (timezone.now() - timedelta(days=30)).isoformat()
        future = (timezone.now() + timedelta(days=2)).isoformat()
        for stamp in (three_days, thirty_days, future):
            _sync(owner_client, store, _op('sale', {'items': [{'productId': str(p.id), 'quantity': 1}]}, created_at=stamp))
        times = sorted(Sale.objects.filter(store=store).values_list('created_at', 'needs_review'))
        assert abs((timezone.now() - timedelta(days=3)) - times[0][0]) < timedelta(minutes=2) and times[0][1] is False
        for when, flagged in times[1:]:
            assert abs(timezone.now() - when) < timedelta(minutes=2) and flagged  # clamped to now, and flagged

    def test_over_limit_cashier_discount_is_flagged_offline(self, cashier_client, store):
        p = _product(store)
        _sync(cashier_client, store, _op('sale', {'items': [{'productId': str(p.id), 'quantity': 2}], 'discount': {'type': 'PERCENT', 'value': '30'}}))
        sale = Sale.objects.get(store=store)
        assert sale.needs_review and 'cashier may give' in sale.review_notes

    def test_customer_operations_need_pro_and_report_it_per_operation(self, owner_client, store):
        c = Customer.objects.create(store=store, name='X')
        r = _sync(owner_client, store, _op('customer_payment', {'customerId': str(c.id), 'amount': '10', 'method': 'CASH'})).data['results'][0]
        assert r['status'] == 'rejected'

    def test_batch_limits(self, owner_client, store):
        assert owner_client.post(f'/api/stores/{store.id}/sync/', {'operations': []}, format='json').status_code == 400
        too_many = [_op('sale', {'items': []}) for _ in range(51)]
        assert owner_client.post(f'/api/stores/{store.id}/sync/', {'operations': too_many}, format='json').status_code == 400


@pytest.mark.django_db
class TestCatalogReviewAndReports:
    def test_catalog_never_contains_cost_prices(self, cashier_client, store):
        _product(store)
        data = cashier_client.get(f'/api/stores/{store.id}/catalog/').data
        assert data['products'] and 'cost_price' not in data['products'][0]
        assert data['currentShift'] is None and 'serverTime' in data

    def test_owner_can_clear_a_review_flag(self, owner_client, cashier_client, store):
        p = _product(store, quantity=1)
        _sync(cashier_client, store, _op('sale', {'items': [{'productId': str(p.id), 'quantity': 3}]}))
        sale = Sale.objects.get(store=store)
        assert owner_client.get(f'/api/stores/{store.id}/sales/').data['summary']['needsReviewCount'] == 1
        assert cashier_client.patch(f'/api/stores/{store.id}/sales/{sale.id}/review/').status_code == 403
        assert owner_client.patch(f'/api/stores/{store.id}/sales/{sale.id}/review/').status_code == 200
        assert owner_client.get(f'/api/stores/{store.id}/sales/').data['summary']['needsReviewCount'] == 0

    def test_daily_report(self, owner_client, cashier_client, store):
        p = _product(store, quantity=50)
        _sell(owner_client, store, p, 2, discount={'type': 'AMOUNT', 'value': '30'})                   # 270 cash
        _sell(owner_client, store, p, 1, payments=[{'method': 'TRANSFER', 'amount': '150'}])           # 150 transfer
        data = owner_client.get(f'/api/stores/{store.id}/reports/daily/').data
        s = data['summary']
        assert s['sales_count'] == 2 and s['discounts'] == 30 and s['gross_sales'] == 450
        assert s['received_by_method']['CASH'] == 270 and s['received_by_method']['TRANSFER'] == 150
        assert data['netSales'] == 420
        assert owner_client.get(f'/api/stores/{store.id}/reports/daily/?date=nope').status_code == 400
        assert cashier_client.get(f'/api/stores/{store.id}/reports/daily/').status_code == 403


@pytest.mark.django_db
class TestBackup:
    def test_pro_owner_downloads_everything(self, owner_client, store, pro):
        _sell(owner_client, store, _product(store), 1)
        r = owner_client.get(f'/api/stores/{store.id}/backup/')
        assert r.status_code == 200 and 'attachment' in r['Content-Disposition']
        import json
        data = json.loads(r.content)
        assert len(data['sales']) == 1 and len(data['products']) == 1 and 'sale_payments' in data

    def test_free_plan_is_asked_to_upgrade_and_staff_are_refused(self, owner_client, manager_client, store):
        assert owner_client.get(f'/api/stores/{store.id}/backup/').status_code == 402
        assert manager_client.get(f'/api/stores/{store.id}/backup/').status_code == 403


@pytest.mark.django_db
class TestCustomersApi:
    def test_free_plan_is_asked_to_upgrade(self, owner_client, store):
        assert owner_client.get(f'/api/stores/{store.id}/customers/').status_code == 402

    def test_crud_balance_and_rules(self, owner_client, cashier_client, store, pro):
        url = f'/api/stores/{store.id}/customers/'
        created = cashier_client.post(url, {'name': '  Ada   Obi ', 'phone': '0801'}, format='json')
        assert created.status_code == 201 and created.data['customer']['name'] == 'Ada Obi'
        cid = created.data['customer']['id']
        assert cashier_client.delete(url + f'{cid}/').status_code == 403
        _sell(owner_client, store, _product(store), 2, customerId=cid, payments=[])
        listing = owner_client.get(url + '?q=ada').data
        assert listing['customers'][0]['balance'] == 300 and listing['totalOwed'] == 300
        assert owner_client.delete(url + f'{cid}/').status_code == 400  # has sales
        assert owner_client.get(url + f'{cid}/statement/').data['sales'][0]['balance_due'] == 300
        assert owner_client.post(url, {'name': '   '}, format='json').status_code == 400
