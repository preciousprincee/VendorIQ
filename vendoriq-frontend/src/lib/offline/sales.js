import api, { isNetworkDown } from '../api'
import * as idb from './idb'
import { enqueue } from './sync'
import { adjustCatalogForSale, adjustCatalogForPayment, stampNow } from './catalog'
import { newId } from './money'

/**
 * Submitting work from the till.
 *
 *   online  -> try the normal (strict) endpoint first: the server can say "not
 *              enough stock" or "discount too high" immediately, while the
 *              cashier is still standing at the counter.
 *   offline, or the request never got an answer (timeout / server hiccup)
 *           -> put it in the outbox. The goods are leaving the shop either
 *              way, so the sale is recorded locally and synced later (the
 *              server then records it leniently and flags anything odd).
 *
 * Either way the same clientId is used, so a request that DID reach the
 * server but whose answer was lost can never be recorded twice.
 */

const KEEP_LOCAL_SALES = 100

// Skip the (slow) live attempt when the browser says offline OR a recent request
// just failed to reach the server - waiting out a 12 s timeout per sale at a
// busy counter is worse than queueing straight away (the sale syncs seconds later).
const worthTrying = () => (typeof navigator === 'undefined' || navigator.onLine !== false) && !isNetworkDown()

const isRetryable = (err) => {
  if (!err.response) return true                        // never reached the server
  const s = err.response.status
  return s === 429 || s >= 500 || err.code === 'ECONNABORTED'
}

async function saveLocalSale(row) {
  await idb.put('localSales', row)
  // Keep the list short: only this store's most recent ones.
  const mine = (await idb.allByIndex('localSales', 'storeId', row.storeId))
    .sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)))
  for (const old of mine.slice(KEEP_LOCAL_SALES)) {
    if (old.status === 'synced') await idb.del('localSales', old.clientId)
  }
}

export async function listLocalSales(storeId) {
  return (await idb.allByIndex('localSales', 'storeId', storeId))
    .sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)))
}

export async function submitSale({ store, user, payload, receipt, credit = 0 }) {
  const clientId = payload.clientId
  const createdAt = stampNow()
  const base = { clientId, storeId: store.id, createdAt, receipt }

  if (worthTrying()) {
    try {
      const { data } = await api.post(`/stores/${store.id}/sales/`, payload, { timeout: 12000 })
      await saveLocalSale({ ...base, status: 'synced', sale: data.sale })
      await adjustCatalogForSale(store.id, payload.items, payload.customerId, credit)
      return { status: 'synced', sale: data.sale }
    } catch (err) {
      if (!isRetryable(err)) throw err   // a real "no" (stock, discount, plan...) - show it, don't queue it
    }
  }

  await saveLocalSale({ ...base, status: 'pending', sale: null })
  await adjustCatalogForSale(store.id, payload.items, payload.customerId, credit)
  await enqueue({
    clientId, storeId: store.id, userId: user.id, type: 'sale', createdAt,
    payload, meta: { customerId: payload.customerId || null, credit },
    label: `Sale ${receipt.receiptNo}`,
  })
  return { status: 'queued' }
}

export async function submitCustomerPayment({ store, user, customer, amount, method }) {
  const clientId = newId()
  const createdAt = stampNow()
  const body = { amount: Number(amount).toFixed(2), method, clientId }

  if (worthTrying()) {
    try {
      const { data } = await api.post(`/stores/${store.id}/customers/${customer.id}/payments/`, body, { timeout: 12000 })
      await adjustCatalogForPayment(store.id, customer.id, Number(amount))
      return { status: 'synced', customer: data.customer }
    } catch (err) {
      if (!isRetryable(err)) throw err
    }
  }

  await adjustCatalogForPayment(store.id, customer.id, Number(amount))
  await enqueue({
    clientId, storeId: store.id, userId: user.id, type: 'customer_payment', createdAt,
    payload: { customerId: customer.id, amount: body.amount, method },
    meta: {}, label: `Payment from ${customer.name}`,
  })
  return { status: 'queued' }
}
