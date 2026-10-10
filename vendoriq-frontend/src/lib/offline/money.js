/**
 * Money maths for the till. Everything is done in whole KOBO (integers) so
 * 0.1 + 0.2 style float drift can never put a kobo out - and the rounding
 * (half up) matches the server's Decimal ROUND_HALF_UP, so the receipt a
 * cashier prints offline shows the same numbers the server later records.
 */
export const toKobo = (n) => Math.round((Number(n) || 0) * 100)
export const fromKobo = (k) => k / 100
export const r2 = (n) => fromKobo(toKobo(n))
// A string the API's DecimalField(decimal_places=2) always accepts.
export const toMoney = (n) => fromKobo(toKobo(n)).toFixed(2)

export const METHODS = [
  { key: 'CASH', label: 'Cash' },
  { key: 'TRANSFER', label: 'Transfer' },
  { key: 'CARD', label: 'Card / POS' },
]
export const methodLabel = (key) => METHODS.find((m) => m.key === key)?.label || key

/** Parses what a person typed into a money box ("1,500", "1500.5", ""). */
export function parseMoney(text) {
  const cleaned = String(text ?? '').replace(/,/g, '').trim()
  if (cleaned === '' || cleaned === '.') return 0
  const n = Number(cleaned)
  return Number.isFinite(n) && n >= 0 ? n : NaN
}

export function computeTotals(lines, discountType, discountValue) {
  const subtotalK = lines.reduce((sum, l) => sum + toKobo(l.price) * l.quantity, 0)
  let discountK = 0
  const value = Number(discountValue) || 0
  if (value > 0) {
    discountK = discountType === 'PERCENT'
      ? Math.round((subtotalK * Math.min(value, 100)) / 100)
      : Math.min(toKobo(value), subtotalK)
  }
  return {
    subtotal: fromKobo(subtotalK),
    discount: fromKobo(discountK),
    total: fromKobo(subtotalK - discountK),
    discountPercent: subtotalK > 0 ? (discountK / subtotalK) * 100 : 0,
  }
}

/**
 * What was handed over -> what the sale records.
 *   tenders  {CASH, TRANSFER, CARD}  numbers the cashier typed (0 = nothing)
 *   mode     'PAY'    must be paid in full today (nothing typed = exact cash)
 *            'CREDIT' whatever is not paid becomes the customer's debt
 * Returns the payment list to send plus change / credit and whether it is sendable.
 */
export function computePayment(total, tenders, mode, hasCustomer) {
  const totalK = toKobo(total)
  const cashK = toKobo(tenders.CASH)
  const nonCashK = toKobo(tenders.TRANSFER) + toKobo(tenders.CARD)
  const anyTender = cashK + nonCashK > 0

  if (!anyTender && mode === 'PAY') {
    return {
      payments: totalK > 0 ? [{ method: 'CASH', amount: toMoney(total) }] : [],
      cashTendered: total, change: 0, credit: 0, short: 0, valid: true, error: '', exact: true,
    }
  }
  const dueK = totalK - nonCashK
  const cashAppliedK = Math.max(0, Math.min(cashK, dueK))
  const changeK = cashK - cashAppliedK
  const creditK = Math.max(0, totalK - nonCashK - cashAppliedK)

  let error = ''
  if (nonCashK > totalK) error = 'Card/transfer is more than the sale total.'
  else if (mode === 'PAY' && creditK > 0) error = `Short by ${fromKobo(creditK).toLocaleString('en-NG')}.`
  else if (mode === 'CREDIT' && !hasCustomer) error = 'Choose a customer to sell on credit.'

  const payments = []
  if (cashK > 0) payments.push({ method: 'CASH', amount: toMoney(tenders.CASH) })
  if (toKobo(tenders.TRANSFER) > 0) payments.push({ method: 'TRANSFER', amount: toMoney(tenders.TRANSFER) })
  if (toKobo(tenders.CARD) > 0) payments.push({ method: 'CARD', amount: toMoney(tenders.CARD) })

  return {
    payments, cashTendered: fromKobo(cashK), change: fromKobo(changeK), credit: fromKobo(creditK),
    short: mode === 'PAY' ? fromKobo(creditK) : 0, valid: !error, error, exact: false,
  }
}

/** Mirrors the server's return maths so the refund can be PREVIEWED. The server is the authority. */
export function previewReturn(sale, picks) {
  const subtotal = Number(sale.subtotal) || 0
  const discount = Number(sale.discount_amount) || 0
  const ratio = subtotal > 0 ? 1 - discount / subtotal : 0
  let valueK = 0
  let allBack = true
  for (const item of sale.sale_items) {
    const qty = picks[item.id] || 0
    valueK += Math.round(toKobo(item.unit_price) * qty * ratio)
    if (qty + item.returned_quantity < item.quantity) allBack = false
  }
  const totalK = toKobo(sale.total_amount)
  if (allBack) valueK = totalK
  valueK = Math.min(valueK, totalK)
  const paidNetK = toKobo(sale.amount_paid) - toKobo(sale.amount_refunded)
  const refundK = Math.max(0, paidNetK - (totalK - valueK))
  return { value: fromKobo(valueK), refund: fromKobo(refundK) }
}

export const newId = () => {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  // Older browsers: RFC4122 v4 from getRandomValues (or, last resort, Math.random).
  const bytes = new Uint8Array(16)
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(bytes)
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
