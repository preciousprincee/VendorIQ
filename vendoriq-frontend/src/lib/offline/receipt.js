import { r2, methodLabel } from './money'

/**
 * One receipt shape for every source: built from the cart (offline - printed
 * before the server has seen the sale) or from a server sale (reprints, the
 * sales list). `receiptNo` is the first 8 characters of the sale's client id,
 * which is also what the server prints, so a receipt matches before AND after sync.
 */
export const receiptNoFrom = (id) => String(id || '').replace(/-/g, '').slice(0, 8).toUpperCase()

export function buildLocalReceipt({ clientId, store, cashier, createdAt, lines, totals, payment, customerName, note }) {
  return {
    receiptNo: receiptNoFrom(clientId),
    createdAt,
    storeName: store.name,
    storeLocation: store.location || '',
    cashier: cashier || '',
    customerName: customerName || '',
    items: lines.map((l) => ({ name: l.name, quantity: l.quantity, returned: 0, unitPrice: l.price, lineTotal: r2(l.price * l.quantity) })),
    subtotal: totals.subtotal,
    discount: totals.discount,
    total: totals.total,
    returned: 0,
    netTotal: totals.total,
    payments: payment.payments.map((p) => ({ method: p.method, amount: Number(p.amount) })),
    cashTendered: payment.cashTendered,
    change: payment.change,
    balanceDue: payment.credit,
    note: note || '',
  }
}

export function receiptFromSale(sale, store) {
  const subtotal = Number(sale.subtotal) || 0
  const discount = Number(sale.discount_amount) || 0
  return {
    receiptNo: sale.receipt_no || receiptNoFrom(sale.client_id || sale.id),
    createdAt: sale.created_at,
    storeName: store.name,
    storeLocation: store.location || '',
    cashier: sale.recorded_by_name || '',
    customerName: sale.customer?.name || '',
    items: (sale.sale_items || []).map((i) => ({
      name: i.product?.name || 'Item', quantity: i.quantity, returned: i.returned_quantity || 0,
      unitPrice: Number(i.unit_price), lineTotal: r2(Number(i.unit_price) * i.quantity),
    })),
    subtotal,
    discount,
    total: r2(subtotal - discount),
    returned: Number(sale.returned_amount) || 0,
    netTotal: Number(sale.total_amount) || 0,
    // Only what was paid at the till - later debt payments are not part of this receipt.
    // The server stores the part of the cash that was APPLIED to the sale (change
    // is not revenue). A receipt reads naturally as "Cash handed over / Change",
    // exactly like the one printed at the till - so show the cash tendered.
    payments: (sale.payments || []).filter((p) => !p.is_debt_payment).map((p) => ({
      method: p.method,
      amount: p.method === 'CASH' && Number(sale.cash_tendered) > Number(p.amount) ? Number(sale.cash_tendered) : Number(p.amount),
    })),
    cashTendered: Number(sale.cash_tendered) || 0,
    change: Number(sale.change_given) || 0,
    balanceDue: Number(sale.balance_due) || 0,
    note: sale.note || '',
  }
}

const money = (n) => `N${Number(n).toLocaleString('en-NG', { minimumFractionDigits: Number.isInteger(Number(n)) ? 0 : 2, maximumFractionDigits: 2 })}`

/** Plain-text receipt for WhatsApp / SMS sharing. */
export function receiptToText(r) {
  const when = new Date(r.createdAt).toLocaleString('en-NG', { dateStyle: 'medium', timeStyle: 'short' })
  const lines = [
    r.storeName,
    r.storeLocation,
    `Receipt #${r.receiptNo} - ${when}`,
    r.customerName ? `Customer: ${r.customerName}` : '',
    '',
    ...r.items.map((i) => `${i.name} x${i.quantity} @ ${money(i.unitPrice)} = ${money(i.lineTotal)}`),
    '',
    r.discount > 0 ? `Subtotal: ${money(r.subtotal)}` : '',
    r.discount > 0 ? `Discount: -${money(r.discount)}` : '',
    `TOTAL: ${money(r.total)}`,
    r.returned > 0 ? `Returned: -${money(r.returned)}` : '',
    ...r.payments.map((p) => `${methodLabel(p.method)}: ${money(p.amount)}`),
    r.change > 0 ? `Change: ${money(r.change)}` : '',
    r.balanceDue > 0 ? `BALANCE OWING: ${money(r.balanceDue)}` : '',
    '',
    'Thank you for your patronage!',
  ]
  return lines.filter((l, i) => l !== '' || lines[i - 1] !== '').join('\n').trim()
}
