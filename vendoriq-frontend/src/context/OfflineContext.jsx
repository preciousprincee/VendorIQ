import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { useAuth } from './AuthContext'
import { useStore } from './StoreContext'
import * as idb from '../lib/offline/idb'
import { flush, subscribe, outboxFor, discard as discardOp, retry as retryOp } from '../lib/offline/sync'
import { refreshCatalog, loadSkew } from '../lib/offline/catalog'
import { track } from '../lib/analytics'

/**
 * Connection state + automatic syncing for the offline till.
 *
 * Syncing is attempted: on app start, when the browser says it's back
 * online, when a request succeeds after a failure, every 30 s while there is
 * work waiting, and when the tab becomes visible again. The catalog (products
 * / customers / shift cached for offline use) is refreshed whenever online.
 */
const OfflineContext = createContext(null)

const CATALOG_REFRESH_MS = 5 * 60 * 1000
const RETRY_MS = 30 * 1000

export function OfflineProvider({ children }) {
  const { user } = useAuth()
  const { activeStore } = useStore()
  const [online, setOnline] = useState(typeof navigator === 'undefined' ? true : navigator.onLine !== false)
  const [pending, setPending] = useState(0)
  const [failed, setFailed] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [catalogVersion, setCatalogVersion] = useState(0) // bumped when the cached catalog changes
  const userId = user?.id

  const readOutbox = useCallback(async () => {
    if (!userId) { setPending(0); setFailed([]); return }
    const rows = await outboxFor(userId)
    setPending(rows.filter((o) => o.status === 'pending').length)
    setFailed(rows.filter((o) => o.status === 'failed'))
  }, [userId])

  const reloadCatalog = useCallback(async () => {
    if (!activeStore?.id || !userId) return
    try {
      await refreshCatalog(activeStore.id)
      setCatalogVersion((v) => v + 1)
    } catch { /* offline or a hiccup - the cached copy stays in use */ }
  }, [activeStore?.id, userId])

  const syncNow = useCallback(async () => {
    if (!userId) return { sent: 0 }
    setSyncing(true)
    try {
      const result = await flush(userId)
      await readOutbox()
      if (result.sent > 0) await reloadCatalog() // server numbers changed (stock, balances)
      return result
    } finally {
      setSyncing(false)
    }
  }, [userId, readOutbox, reloadCatalog])

  const syncRef = useRef(syncNow)
  const reloadRef = useRef(reloadCatalog)
  useEffect(() => { syncRef.current = syncNow; reloadRef.current = reloadCatalog })

  // One event each time the connection is LOST (not on every flicker of the same outage).
  const wasOnline = useRef(true)
  useEffect(() => {
    if (wasOnline.current && !online && userId) track('offline_mode_entered', { pending_sales: pending })
    wasOnline.current = online
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `pending` is just context for the event, not a trigger
  }, [online, userId])

  // Outbox changes (from anywhere) -> refresh the counters.
  useEffect(() => {
    loadSkew().catch(() => {})
    readOutbox()
    return subscribe(readOutbox)
  }, [readOutbox])

  // Connection signals.
  useEffect(() => {
    const goOnline = () => { setOnline(true); syncRef.current(); reloadRef.current() }
    const goOffline = () => setOnline(false)
    const onNetwork = (e) => {
      const down = !!e.detail?.down
      setOnline(!down)
      if (!down) syncRef.current()   // a request just succeeded after failing: connection is back
    }
    const onVisible = () => { if (document.visibilityState === 'visible') { syncRef.current(); reloadRef.current() } }
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    window.addEventListener('viq:network', onNetwork)
    const onCatalogChanged = () => setCatalogVersion((v) => v + 1)
    window.addEventListener('viq:catalog-changed', onCatalogChanged)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('viq:network', onNetwork)
      window.removeEventListener('viq:catalog-changed', onCatalogChanged)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  // Initial + periodic work, only while signed in.
  useEffect(() => {
    if (!userId) return undefined
    syncRef.current()
    const retryTimer = setInterval(() => { readOutbox().then(() => syncRef.current()) }, RETRY_MS)
    return () => clearInterval(retryTimer)
  }, [userId, readOutbox])

  useEffect(() => {
    if (!activeStore?.id || !userId) return undefined
    reloadRef.current()
    const t = setInterval(() => reloadRef.current(), CATALOG_REFRESH_MS)
    return () => clearInterval(t)
  }, [activeStore?.id, userId])

  // Warm the barcode-scanner chunk while we still have a connection, so the
  // scanner also opens offline (the service worker caches it on first load).
  useEffect(() => {
    if (!online || !userId) return undefined
    const t = setTimeout(() => {
      import('@zxing/browser').catch(() => {})
      import('@zxing/library').catch(() => {})
    }, 4000)
    return () => clearTimeout(t)
  }, [online, userId])

  // Signing out with sales still waiting to sync is not harmful (they stay on
  // the device and send the next time THIS person signs in) - but it is
  // surprising, so ask first.
  const confirmLogout = useCallback(() => {
    const waiting = pending + failed.length
    if (waiting === 0) return true
    return window.confirm(`${waiting} offline ${waiting === 1 ? 'item has' : 'items have'} not been synced yet. They stay on this device and sync the next time you sign in with internet. Sign out anyway?`)
  }, [pending, failed.length])

  const discard = useCallback(async (clientId) => { await discardOp(clientId); await readOutbox(); reloadCatalog() }, [readOutbox, reloadCatalog])
  const retry = useCallback(async (clientId) => { await retryOp(clientId); await readOutbox() }, [readOutbox])

  return (
    <OfflineContext.Provider value={{
      online, pending, failed, syncing, catalogVersion, persistent: idb.isPersistent(),
      syncNow, reloadCatalog, discard, retry, refreshOutbox: readOutbox, confirmLogout,
    }}>
      {children}
    </OfflineContext.Provider>
  )
}

export const useOffline = () => {
  const ctx = useContext(OfflineContext)
  if (!ctx) throw new Error('useOffline must be used within OfflineProvider')
  return ctx
}
