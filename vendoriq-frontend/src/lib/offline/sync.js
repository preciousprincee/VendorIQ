import api, { isNetworkError } from '../api'
import * as idb from './idb'
import { track } from '../analytics'

/**
 * The outbox: everything done while offline (sales, debt payments) waits
 * here until it reaches the server. Safe to retry forever because every
 * operation carries a clientId the server de-duplicates on.
 *
 *   status 'pending'  waiting to be sent (retried automatically)
 *   status 'failed'   the server said NO (e.g. the product was deleted) -
 *                     needs a person: Retry or Discard
 */
const listeners = new Set()
let flushing = null

export const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }
const emit = () => listeners.forEach((fn) => { try { fn() } catch { /* a listener must never break sync */ } })

const BATCH = 20
const MAX_RETRYABLE_ATTEMPTS = 8

export async function enqueue(op) {
  await idb.put('outbox', { status: 'pending', attempts: 0, error: '', ...op })
  emit()
  // Try straight away if we think we're online - the common case is a
  // momentary blip, and the cashier shouldn't wait for the 30s timer.
  if (typeof navigator === 'undefined' || navigator.onLine !== false) {
    // ...but only THIS person's work: another cashier's older unsynced sales
    // may still be on the device and must never be sent under this login.
    setTimeout(() => { flush(op.userId).catch(() => {}) }, 50)
  }
}

export async function outboxFor(userId) {
  const rows = await idb.all('outbox')
  return rows.filter((o) => !userId || o.userId === userId)
}

export async function discard(clientId) {
  const op = await idb.get('outbox', clientId)
  await idb.del('outbox', clientId)
  if (op?.type === 'sale') await patchLocalSale(clientId, { status: 'discarded' })
  emit()
}

export async function retry(clientId) {
  const op = await idb.get('outbox', clientId)
  if (!op) return
  await idb.put('outbox', { ...op, status: 'pending', attempts: 0, error: '' })
  if (op.type === 'sale') await patchLocalSale(clientId, { status: 'pending', error: '' })
  emit()
  flush(op.userId).catch(() => {})
}

async function patchLocalSale(clientId, patch) {
  const row = await idb.get('localSales', clientId)
  if (row) await idb.put('localSales', { ...row, ...patch })
}

async function settle(op, result) {
  await idb.del('outbox', op.clientId)
  if (op.type === 'sale') await patchLocalSale(op.clientId, { status: 'synced', sale: result.sale || null, error: '' })
}

async function fail(op, message) {
  await idb.put('outbox', { ...op, status: 'failed', error: message })
  if (op.type === 'sale') await patchLocalSale(op.clientId, { status: 'failed', error: message })
}

const messageOf = (err) => err?.response?.data?.error || err?.response?.data?.detail || err?.message || 'Rejected by the server'

/**
 * Send everything that is pending for this user. One run at a time; callers
 * share the same promise. Resolves with {sent, offline?, retryLater?}.
 */
export function flush(userId) {
  if (flushing) return flushing
  flushing = run(userId).finally(() => { flushing = null; emit() })
  return flushing
}

async function run(userId) {
  const pending = (await idb.all('outbox'))
    .filter((o) => o.status === 'pending' && (!userId || o.userId === userId))
    .sort((a, b) => String(a.createdAt).localeCompare(String(b.createdAt)))
  if (!pending.length) return { sent: 0 }

  const byStore = new Map()
  pending.forEach((op) => byStore.set(op.storeId, [...(byStore.get(op.storeId) || []), op]))

  let sent = 0
  for (const [storeId, ops] of byStore) {
    for (let i = 0; i < ops.length; i += BATCH) {
      const chunk = ops.slice(i, i + BATCH)
      let data
      try {
        const res = await api.post(`/stores/${storeId}/sync/`, {
          operations: chunk.map((o) => ({ type: o.type, clientId: o.clientId, createdAt: o.createdAt, payload: o.payload })),
        }, { timeout: 30000 })
        data = res.data
      } catch (err) {
        if (isNetworkError(err)) return { sent, offline: true }
        const status = err.response?.status
        if (status === 401) return { sent }                 // the API client refreshes/redirects; try again next tick
        if (status === 429 || status >= 500) return { sent, retryLater: true }
        // 400/403/404: the server will never accept this batch as it is.
        for (const op of chunk) await fail(op, messageOf(err))
        continue
      }

      const byId = new Map(chunk.map((o) => [o.clientId, o]))
      for (const result of data.results || []) {
        const op = byId.get(result.clientId)
        if (!op) continue
        if (result.status === 'synced' || result.status === 'duplicate') {
          await settle(op, result)
          sent += 1
          // 'duplicate' = the server already had it (an earlier attempt got through): not a new delivery.
          if (op.type === 'sale' && result.status === 'synced') {
            const waited = Math.round((Date.now() - Date.parse(op.createdAt)) / 1000)
            track('sale_synced', { queued_seconds: Number.isFinite(waited) && waited >= 0 ? waited : undefined, attempts: op.attempts })
          }
        } else if (result.retryable && op.attempts + 1 < MAX_RETRYABLE_ATTEMPTS) {
          await idb.put('outbox', { ...op, attempts: op.attempts + 1 })
        } else {
          await fail(op, result.error || 'Rejected by the server')
        }
      }
    }
  }
  return { sent }
}
