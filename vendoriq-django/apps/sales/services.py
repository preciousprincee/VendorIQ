"""
All POS money logic lives here - sales, returns, debt payments, till
(shift) maths - so the online endpoints and the offline-sync endpoint run the
SAME code and can't drift apart.

Two modes for recording a sale:

  strict  (a normal online sale)   refuse anything wrong: not enough stock,
                                   discount over the cashier's limit...
  lenient (replaying an offline    the goods have ALREADY left the shop, so
           sale from the outbox)   refusing would only create a record that
                                   disagrees with reality. Record the sale,
                                   clamp what must be clamped, and flag it
                                   for the owner (Sale.needs_review).
"""
import logging
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, F
from django.utils import timezone

from apps.billing.entitlements import require_customer_management
from apps.customers.models import Customer, CustomerPayment
from apps.products.models import Product
from apps.stores.models import Staff
from .models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem, Shift

logger = logging.getLogger(__name__)

ZERO = Decimal('0')
METHODS = ('CASH', 'TRANSFER', 'CARD')

# How far back / forward an offline device's clock is believed.
MAX_BACKDATE = timedelta(days=7)
MAX_FUTURE = timedelta(minutes=5)


class SaleError(Exception):
    """A problem the person can act on. `status` is the HTTP status the view should use."""
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def q2(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def resolve_time(client_time, now):
    """
    A sale rung up offline keeps the time it HAPPENED (so it lands on the right
    day's report), but a device clock can be wrong or tampered with, so the
    time is only believed inside a sane window. Returns (time, note|None).
    """
    if client_time is None:
        return now, None
    if client_time > now + MAX_FUTURE:
        return now, 'Device clock was ahead - sale time set to when it reached the server.'
    if client_time < now - MAX_BACKDATE:
        return now, 'Sale was more than 7 days old when it synced - dated to when it reached the server.'
    return min(client_time, now), None


def _discount_amount(subtotal, discount):
    if not discount:
        return ZERO
    kind, value = discount['type'], Decimal(discount['value'])
    if value < 0:
        raise SaleError('Discount cannot be negative.')
    if kind == 'PERCENT':
        if value > 100:
            raise SaleError('Discount cannot be more than 100%.')
        return q2(subtotal * value / 100)
    if value > subtotal:
        raise SaleError('Discount cannot be more than the sale total.')
    return q2(value)


# ---------------------------------------------------------------------------
# Recording a sale
# ---------------------------------------------------------------------------

def create_sale(*, store, user, role, data, lenient=False, client_time=None):
    """
    data (already validated by RecordSaleSerializer):
      items [{productId, quantity, unitPrice?}], discount {type,value}?,
      customerId?, payments [{method, amount}]?, clientId?, note?
    Returns (sale, created). created=False means this clientId was already recorded.
    """
    client_id = data.get('clientId')
    if client_id:
        existing = Sale.objects.filter(store=store, client_id=client_id).first()
        if existing is not None:
            return existing, False

    now = timezone.now()
    sold_at, time_note = resolve_time(client_time, now) if lenient else (now, None)
    flags = [time_note] if time_note else []

    staff = Staff.objects.filter(store=store, user=user).first()

    # Customer (a Pro feature) - checked before any stock is touched.
    customer = None
    if data.get('customerId'):
        require_customer_management(store.owner)
        customer = Customer.objects.filter(id=data['customerId'], store=store).first()
        if customer is None:
            raise SaleError('Customer not found.', 404)

    try:
        with transaction.atomic():
            lines, subtotal, cost_total = [], ZERO, ZERO

            # Lock products in a CONSISTENT order (by id): two simultaneous
            # sales listing the same products in opposite order would
            # otherwise deadlock.
            for item in sorted(data['items'], key=lambda i: str(i['productId'])):
                product = Product.objects.select_for_update().filter(id=item['productId'], store=store).first()
                if product is None:
                    raise SaleError('A product in this sale no longer exists.', 404)
                qty = item['quantity']

                if product.quantity < qty:
                    if not lenient:
                        raise SaleError(f'Insufficient stock for {product.name}. Available: {product.quantity}')
                    flags.append(f'{product.name}: sold {qty} but only {max(product.quantity, 0)} were recorded in stock.')

                unit_price = product.selling_price
                if lenient and item.get('unitPrice') is not None:
                    # Offline: the customer was charged the price the till SHOWED
                    # at the time. Honour it, but say so if it has since changed.
                    sent = q2(item['unitPrice'])
                    if sent != product.selling_price:
                        flags.append(f'{product.name}: charged {sent}, current price is {product.selling_price}.')
                    unit_price = sent

                unit_cost = product.cost_price
                lines.append({'product': product, 'quantity': qty, 'unit_price': unit_price, 'unit_cost': unit_cost,
                              'profit': (unit_price - unit_cost) * qty})
                subtotal += unit_price * qty
                cost_total += unit_cost * qty

                product.quantity = max(0, product.quantity - qty)
                product.save(update_fields=['quantity', 'updated_at'])

            subtotal = q2(subtotal)
            discount = _discount_amount(subtotal, data.get('discount'))
            if discount > 0 and role == 'CASHIER' and subtotal > 0:
                limit = Decimal(settings.CASHIER_MAX_DISCOUNT_PERCENT)
                if discount * 100 > subtotal * limit:
                    msg = f'Discount is above the {limit}% a cashier may give.'
                    if not lenient:
                        raise SaleError(msg + ' Ask a manager.', 403)
                    flags.append(msg)
            total_due = q2(subtotal - discount)

            paid_rows, cash_tendered, change, credit = _apply_payments(data.get('payments'), total_due)
            if credit > 0 and customer is None:
                raise SaleError('Choose a customer to sell on credit (part or all of the sale is unpaid).')
            amount_paid = sum((amt for _m, amt in paid_rows), ZERO)

            sale = Sale.objects.create(
                store=store, staff=staff, recorded_by=user, customer=customer,
                subtotal=subtotal, discount_amount=discount,
                total_amount=total_due, total_profit=q2(total_due - cost_total),
                amount_paid=amount_paid, credit_amount=credit,
                cash_tendered=cash_tendered, change_given=change,
                note=(data.get('note') or '')[:200],
                client_id=client_id,
                synced_at=now if lenient else None,
                needs_review=bool(flags), review_notes='\n'.join(flags),
            )
            if sold_at != now:
                Sale.objects.filter(pk=sale.pk).update(created_at=sold_at)  # auto_now_add can't be set on create
                sale.created_at = sold_at

            SaleItem.objects.bulk_create([SaleItem(sale=sale, **line) for line in lines])
            SalePayment.objects.bulk_create([
                SalePayment(sale=sale, method=m, amount=amt, recorded_by=user, created_at=sold_at) for m, amt in paid_rows
            ])
    except IntegrityError:
        # Two requests carrying the SAME clientId raced; the unique index let
        # exactly one through. The loser must answer with the winner's sale,
        # not a 500 (a retrying phone would otherwise see an error for a sale
        # that DID go through).
        existing = Sale.objects.filter(store=store, client_id=client_id).first() if client_id else None
        if existing is None:
            raise
        return existing, False
    return sale, True


def _apply_payments(payments, total_due):
    """
    Turns what the customer handed over into payment rows.
    Returns (rows [(method, amount)], cash_tendered, change, credit_left_unpaid).

    payments=None  -> the old behaviour: paid in full, in cash.
    Cash can be over-tendered (that is what "change" is); card/transfer cannot.
    Anything not covered becomes credit (needs a customer - checked by the caller).
    """
    if payments is None:
        return ([('CASH', total_due)] if total_due > 0 else []), total_due, ZERO, ZERO

    by_method = {}
    for p in payments:
        by_method[p['method']] = by_method.get(p['method'], ZERO) + q2(p['amount'])

    non_cash = sum((amt for m, amt in by_method.items() if m != 'CASH'), ZERO)
    if non_cash > total_due:
        raise SaleError('Card/transfer payments are more than the sale total.')
    tendered = by_method.get('CASH', ZERO)
    cash_applied = min(tendered, total_due - non_cash)
    change = q2(tendered - cash_applied)

    rows = [(m, amt) for m, amt in by_method.items() if m != 'CASH' and amt > 0]
    if cash_applied > 0:
        rows.insert(0, ('CASH', q2(cash_applied)))
    credit = q2(total_due - non_cash - cash_applied)
    return rows, tendered, change, credit


# ---------------------------------------------------------------------------
# Returns / refunds
# ---------------------------------------------------------------------------

def record_return(*, store, user, sale_id, items, refund_method='', restock=True, reason=''):
    """
    items: [{saleItemId, quantity}]. Reduces the sale's NET figures (so every
    report follows), puts the goods back in stock if asked, and works out how
    much money (if any) has to go back to the customer.
    """
    with transaction.atomic():
        sale = Sale.objects.select_for_update().filter(id=sale_id, store=store).first()
        if sale is None:
            raise SaleError('Sale not found.', 404)

        sale_items = {str(i.id): i for i in SaleItem.objects.select_for_update().filter(sale=sale).select_related('product')}
        wanted = {}
        for row in items:
            key = str(row['saleItemId'])
            if key not in sale_items:
                raise SaleError('That item is not part of this sale.')
            wanted[key] = wanted.get(key, 0) + row['quantity']

        value = ZERO
        for key, qty in wanted.items():
            item = sale_items[key]
            if qty > item.quantity - item.returned_quantity:
                raise SaleError(f'Only {item.quantity - item.returned_quantity} of {item.product.name} can still be returned.')
            gross = item.unit_price * qty
            # The sale-level discount is shared across the lines pro-rata.
            value += gross * (1 - sale.discount_amount / sale.subtotal) if sale.subtotal > 0 else ZERO
        value = q2(value)

        fully_returned = all(
            (wanted.get(k, 0) + i.returned_quantity) >= i.quantity for k, i in sale_items.items()
        )
        if fully_returned:
            value = sale.total_amount  # absorb any kobo of rounding so a full return lands on exactly zero
        value = min(value, sale.total_amount)

        new_total = q2(sale.total_amount - value)
        cost_remaining = sum(
            (i.unit_cost * (i.quantity - i.returned_quantity - wanted.get(k, 0)) for k, i in sale_items.items()), ZERO,
        )
        paid_net = sale.amount_paid - sale.amount_refunded
        refund = q2(max(ZERO, paid_net - new_total))
        if refund > 0 and refund_method not in METHODS:
            raise SaleError('Choose how the refund was paid (cash, transfer or card).')
        if refund == 0:
            refund_method = ''

        for key, qty in sorted(wanted.items(), key=lambda kv: str(sale_items[kv[0]].product_id)):
            item = sale_items[key]
            item.returned_quantity += qty
            item.save(update_fields=['returned_quantity'])
            if restock:
                product = Product.objects.select_for_update().get(id=item.product_id)
                product.quantity += qty
                product.save(update_fields=['quantity', 'updated_at'])

        sale.total_amount = new_total
        sale.total_profit = q2(new_total - cost_remaining)
        sale.returned_amount = q2(sale.returned_amount + value)
        sale.amount_refunded = q2(sale.amount_refunded + refund)
        sale.save(update_fields=['total_amount', 'total_profit', 'returned_amount', 'amount_refunded'])

        ret = SaleReturn.objects.create(
            sale=sale, return_value=value, refund_amount=refund, refund_method=refund_method,
            restocked=restock, reason=(reason or '')[:200], recorded_by=user,
        )
        SaleReturnItem.objects.bulk_create([SaleReturnItem(sale_return=ret, sale_item_id=k, quantity=q) for k, q in wanted.items()])
    return sale, ret


# ---------------------------------------------------------------------------
# Customer debt payments
# ---------------------------------------------------------------------------

def customer_balance(customer):
    row = customer.sales.aggregate(t=Sum('total_amount'), p=Sum('amount_paid'), r=Sum('amount_refunded'))
    return (row['t'] or ZERO) - (row['p'] or ZERO) + (row['r'] or ZERO)


def collect_customer_payment(*, store, user, customer_id, amount, method, client_id=None, client_time=None, lenient=False):
    """
    Customer pays off (part of) what they owe. Spread across their oldest
    unpaid sales first. Returns (payment, created); created=False when this
    client_id was already applied.
    """
    require_customer_management(store.owner)
    if client_id:
        existing = CustomerPayment.objects.filter(store=store, client_id=client_id).first()
        if existing is not None:
            return existing, False
    if method not in METHODS:
        raise SaleError('Choose how they paid (cash, transfer or card).')
    amount = q2(amount)
    if amount <= 0:
        raise SaleError('Enter an amount greater than zero.')

    now = timezone.now()
    paid_at, _note = resolve_time(client_time, now) if lenient else (now, None)

    with transaction.atomic():
        customer = Customer.objects.select_for_update().filter(id=customer_id, store=store).first()
        if customer is None:
            raise SaleError('Customer not found.', 404)

        sales = list(Sale.objects.select_for_update().filter(store=store, customer=customer).order_by('created_at'))
        owing = [(s, s.balance_due) for s in sales if s.balance_due > 0]
        total_owed = sum((b for _s, b in owing), ZERO)
        if amount > total_owed:
            raise SaleError(f'That is more than the customer owes ({total_owed}).')

        try:
            with transaction.atomic():
                payment = CustomerPayment.objects.create(
                    store=store, customer=customer, amount=amount, method=method, recorded_by=user,
                    client_id=client_id, created_at=paid_at,
                )
        except IntegrityError:
            existing = CustomerPayment.objects.filter(store=store, client_id=client_id).first() if client_id else None
            if existing is None:
                raise
            return existing, False
        remaining = amount
        for sale, balance in owing:
            if remaining <= 0:
                break
            slice_ = min(remaining, balance)
            SalePayment.objects.create(sale=sale, method=method, amount=slice_, recorded_by=user, customer_payment=payment, created_at=paid_at)
            sale.amount_paid = q2(sale.amount_paid + slice_)
            sale.save(update_fields=['amount_paid'])
            remaining -= slice_
    return payment, True


# ---------------------------------------------------------------------------
# Till / shift maths and the end-of-day summary
# ---------------------------------------------------------------------------

def build_summary(store, start, end, user=None):
    """
    Everything that moved through the till between start and end (optionally
    just one person's). All values are Decimals; the view converts for JSON.
    """
    sales = Sale.objects.filter(store=store, created_at__gte=start, created_at__lt=end)
    pays = SalePayment.objects.filter(sale__store=store, created_at__gte=start, created_at__lt=end)
    rets = SaleReturn.objects.filter(sale__store=store, created_at__gte=start, created_at__lt=end)
    if user is not None:
        sales, pays, rets = sales.filter(recorded_by=user), pays.filter(recorded_by=user), rets.filter(recorded_by=user)

    s = sales.aggregate(n=Count('id'), subtotal=Sum('subtotal'), discount=Sum('discount_amount'), credit=Sum('credit_amount'))
    received = {m: ZERO for m in METHODS}
    collected = {m: ZERO for m in METHODS}
    for row in pays.values('method', 'customer_payment_id').annotate(t=Sum('amount')):
        bucket = collected if row['customer_payment_id'] else received
        bucket[row['method']] += row['t'] or ZERO
    refunded = {m: ZERO for m in METHODS}
    for row in rets.exclude(refund_method='').values('refund_method').annotate(t=Sum('refund_amount')):
        refunded[row['refund_method']] += row['t'] or ZERO
    r = rets.aggregate(n=Count('id'), value=Sum('return_value'))

    cash_in = received['CASH'] + collected['CASH']
    return {
        'sales_count': s['n'] or 0,
        'gross_sales': s['subtotal'] or ZERO,
        'discounts': s['discount'] or ZERO,
        'credit_given': s['credit'] or ZERO,
        'returns_count': r['n'] or 0,
        'returns_value': r['value'] or ZERO,
        'received_by_method': received,        # paid at the time of sale
        'debt_collected_by_method': collected, # later payments against credit
        'refunded_by_method': refunded,
        'cash_in': cash_in,
        'cash_out': refunded['CASH'],
        'net_cash_movement': cash_in - refunded['CASH'],
        'total_received': sum(received.values(), ZERO) + sum(collected.values(), ZERO),
    }


def shift_window(shift, now=None):
    return shift.opened_at, (shift.closed_at or (now or timezone.now())) + timedelta(seconds=1)


def shift_expected_cash(shift, now=None):
    start, end = shift_window(shift, now)
    summary = build_summary(shift.store, start, end, user=shift.opened_by)
    return q2(shift.opening_float + summary['net_cash_movement']), summary


def open_shift(*, store, user, opening_float):
    opening_float = q2(opening_float)
    if opening_float < 0:
        raise SaleError('Opening cash cannot be negative.')
    if Shift.objects.filter(store=store, opened_by=user, closed_at__isnull=True).exists():
        raise SaleError('You already have a shift open.')
    try:
        with transaction.atomic():
            return Shift.objects.create(store=store, opened_by=user, opening_float=opening_float)
    except Exception:
        # The partial unique index closes the race two taps could still win.
        if Shift.objects.filter(store=store, opened_by=user, closed_at__isnull=True).exists():
            raise SaleError('You already have a shift open.')
        raise


def close_shift(*, shift, user, counted_cash, notes=''):
    counted = q2(counted_cash)
    if counted < 0:
        raise SaleError('Counted cash cannot be negative.')
    with transaction.atomic():
        shift = Shift.objects.select_for_update().get(pk=shift.pk)
        if shift.closed_at is not None:
            raise SaleError('This shift is already closed.')
        now = timezone.now()
        shift.closed_at = now
        expected, _summary = shift_expected_cash(shift, now)
        shift.closed_by = user
        shift.expected_cash = expected
        shift.counted_cash = counted
        shift.variance = q2(counted - expected)
        shift.notes = (notes or '')[:300]
        shift.save()
    return shift
