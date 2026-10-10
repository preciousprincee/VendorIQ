/**
 * Minimal promise wrapper around IndexedDB - no dependency, because the
 * offline till has to keep working with nothing but the browser.
 *
 * Object stores
 *   kv          {key, value}              small settings (clock skew...)
 *   catalog     {storeId, products, customers, ...}   what the till needs offline
 *   outbox      {clientId, storeId, userId, type, payload, createdAt, status, ...}  work waiting to reach the server
 *   localSales  {clientId, storeId, status, receipt, sale?}  sales rung up on THIS device (for receipts + the pending list)
 *
 * If IndexedDB is unavailable (some private-browsing modes) everything falls
 * back to memory so the app still works - but then unsynced work is lost on
 * reload, so `isPersistent()` lets the UI warn about it.
 */
const DB_NAME = 'vendoriq-offline'
const VERSION = 1

const SCHEMA = {
  kv: { keyPath: 'key', indexes: [] },
  catalog: { keyPath: 'storeId', indexes: [] },
  outbox: { keyPath: 'clientId', indexes: ['storeId'] },
  localSales: { keyPath: 'clientId', indexes: ['storeId'] },
}

let dbPromise = null
let memoryMode = false
const memory = Object.fromEntries(Object.keys(SCHEMA).map((name) => [name, new Map()]))

function open() {
  if (memoryMode) return Promise.resolve(null)
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve) => {
    if (typeof indexedDB === 'undefined') { memoryMode = true; resolve(null); return }
    let request
    try { request = indexedDB.open(DB_NAME, VERSION) } catch { memoryMode = true; resolve(null); return }
    request.onupgradeneeded = () => {
      const db = request.result
      for (const [name, { keyPath, indexes }] of Object.entries(SCHEMA)) {
        if (db.objectStoreNames.contains(name)) continue
        const store = db.createObjectStore(name, { keyPath })
        indexes.forEach((field) => store.createIndex(field, field))
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => { memoryMode = true; resolve(null) }
    request.onblocked = () => { memoryMode = true; resolve(null) }
  })
  return dbPromise
}

export const isPersistent = () => !memoryMode

function run(storeName, mode, fn) {
  return open().then((db) => {
    if (!db) return null
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, mode)
      const store = tx.objectStore(storeName)
      let result
      try { result = fn(store) } catch (err) { reject(err); return }
      tx.oncomplete = () => resolve(result && 'result' in result ? result.result : undefined)
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error)
    })
  })
}

export async function get(storeName, key) {
  const db = await open()
  if (!db) return memory[storeName].get(key)
  return new Promise((resolve, reject) => {
    const req = db.transaction(storeName, 'readonly').objectStore(storeName).get(key)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function put(storeName, value) {
  const db = await open()
  if (!db) { memory[storeName].set(value[SCHEMA[storeName].keyPath], value); return }
  await run(storeName, 'readwrite', (store) => store.put(value))
}

export async function del(storeName, key) {
  const db = await open()
  if (!db) { memory[storeName].delete(key); return }
  await run(storeName, 'readwrite', (store) => store.delete(key))
}

export async function all(storeName) {
  const db = await open()
  if (!db) return [...memory[storeName].values()]
  return new Promise((resolve, reject) => {
    const req = db.transaction(storeName, 'readonly').objectStore(storeName).getAll()
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}

export async function allByIndex(storeName, index, value) {
  const db = await open()
  if (!db) return [...memory[storeName].values()].filter((row) => row[index] === value)
  return new Promise((resolve, reject) => {
    const req = db.transaction(storeName, 'readonly').objectStore(storeName).index(index).getAll(value)
    req.onsuccess = () => resolve(req.result || [])
    req.onerror = () => reject(req.error)
  })
}
