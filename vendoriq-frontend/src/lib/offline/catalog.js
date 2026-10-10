import api from '../api'
import * as idb from './idb'

/**
 * The till's offline copy of the shop: products (no cost prices - the server
 * never sends them to the till), customers with balances, and the person's
 * open shift. Refreshed whenever there is a connection; read from disk when
 * there isn't.
 */

let skewMs = 0 // serverTime - deviceTime, so offline sale timestamps are right even if the phone's clock is wrong

export const getSkew = () => skewMs
export async function loadSkew() {
  const row = await idb.get('kv', 'skew')
  if (row && Number.isFinite(row.value)) skewMs = row.value
}
export const stampNow = () => new Date(Date.now() + skewMs).toISOString()

export const getCatalog = (storeId) => idb.get('catalog', storeId)

// Tells the UI that the cached catalog changed on disk (a sale just took
// stock out of it) so screens re-read it - the offline path has no network
// refresh to trigger that.
const announceChange = () => window.dispatchEvent(new Event('viq:catalog-changed'))

export async function refreshCatalog(storeId) {
  const { data } = await api.get(`/stores/${storeId}/catalog/`, { timeout: 20000 })
  skewMs = new Date(data.serverTime).getTime() - Date.now()
  await idb.put('kv', { key: 'skew', value: skewMs })

  const catalog = { ...data, storeId, savedAt: Date.now() }
  await applyPendingWork(catalog)
  await idb.put('catalog', catalog)
  return catalog
}

/**
 * The server's numbers don't include sales still waiting in the outbox, so
 * subtract them again - otherwise a refresh would "restore" stock that has
 * already left the shop and let the cashier oversell it.
 */
async function applyPendingWork(catalog) {
  const ops = (await idb.allByIndex('outbox', 'storeId', catalog.storeId)).filter((o) => o.status === 'pending')
  if (!ops.length) return
  const products = new Map(catalog.products.map((p) => [p.id, p]))
  const customers = new Map(catalog.customers.map((c) => [c.id, c]))
  for (const op of ops) {
    if (op.type === 'sale') {
      for (const item of op.payload.items) {
        const p = products.get(item.productId)
        if (p) p.quantity = Math.max(0, p.quantity - item.quantity)
      }
      const c = customers.get(op.meta?.customerId)
      if (c) c.balance += op.meta?.credit || 0
    } else if (op.type === 'customer_payment') {
      const c = customers.get(op.payload.customerId)
      if (c) c.balance -= Number(op.payload.amount) || 0
    }
  }
}

/** Reflect a sale in the cached catalog straight away (stock down, customer balance up). */
export async function adjustCatalogForSale(storeId, items, customerId, credit) {
  const catalog = await getCatalog(storeId)
  if (!catalog) return
  const byId = new Map(catalog.products.map((p) => [p.id, p]))
  for (const item of items) {
    const p = byId.get(item.productId)
    if (p) p.quantity = Math.max(0, p.quantity - item.quantity)
  }
  if (customerId && credit) {
    const c = catalog.customers.find((x) => x.id === customerId)
    if (c) c.balance += credit
  }
  await idb.put('catalog', catalog)
  announceChange()
}

export async function adjustCatalogForPayment(storeId, customerId, amount) {
  const catalog = await getCatalog(storeId)
  const c = catalog?.customers.find((x) => x.id === customerId)
  if (!c) return
  c.balance -= amount
  await idb.put('catalog', catalog)
  announceChange()
}

export async function saveCatalogShift(storeId, shift) {
  const catalog = await getCatalog(storeId)
  if (!catalog) return
  catalog.currentShift = shift
  await idb.put('catalog', catalog)
  announceChange()
}
