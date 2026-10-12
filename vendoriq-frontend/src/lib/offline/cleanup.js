import * as idb from './idb'

/**
 * Called when someone signs out (or the server ends their session). Removes what the till cached for
 * OFFLINE use that contains other people's personal data - the catalog (customer names and phone numbers,
 * the product list) and receipts of sales that have already reached the server - so the next person to
 * use a shared phone or till can't find them in the browser's storage.
 *
 * Deliberately KEEPS everything still waiting to be sent (the outbox, and local rows for sales that are
 * not synced yet): those are real sales that have not reached the server, and deleting them would lose
 * money. They are only ever sent by the same user who rang them up (see sync.flush).
 */
export async function wipeOfflineCaches() {
  try {
    for (const row of await idb.all('catalog')) await idb.del('catalog', row.storeId)
    for (const row of await idb.all('localSales')) {
      if (row.status === 'synced') await idb.del('localSales', row.clientId)
    }
  } catch {
    /* storage unavailable: nothing to clean, and signing out must never fail because of it */
  }
}
