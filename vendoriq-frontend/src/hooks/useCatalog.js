import { useEffect, useState } from 'react'
import { getCatalog } from '../lib/offline/catalog'
import { useOffline } from '../context/OfflineContext'

/**
 * The till's cached shop data for one store: { products, customers,
 * customersEnabled, currentShift, maxCashierDiscountPercent, ... } or null
 * until the first successful download. It re-reads from disk whenever the
 * background refresh (or a sale) changes it, so the screen always shows the
 * latest local truth - online or not.
 */
export function useCatalog(storeId) {
  const { catalogVersion, reloadCatalog } = useOffline()
  const [catalog, setCatalog] = useState(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    if (!storeId) { setCatalog(null); setLoaded(true); return undefined }
    getCatalog(storeId).then((row) => {
      if (cancelled) return
      setCatalog(row ? { ...row, products: [...row.products], customers: [...row.customers] } : null)
      setLoaded(true)
    })
    return () => { cancelled = true }
  }, [storeId, catalogVersion])

  return { catalog, loaded, reload: reloadCatalog }
}
