import { useEffect } from 'react'
import { X } from 'lucide-react'
import { useOffline } from '../../context/OfflineContext'
import { formatDateTime } from '../../lib/utils'

/**
 * Offline work the server refused (e.g. a product in the sale was deleted
 * meanwhile). Nothing is silently dropped: each item stays here with the
 * server's reason until the person retries it or discards it.
 */
export default function SyncIssuesModal({ onClose }) {
  const { failed, retry, discard } = useOffline()

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => { if (failed.length === 0) onClose() }, [failed.length, onClose])

  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-labelledby="sync-issues-title"
        className="card w-full sm:max-w-md max-h-[85vh] flex flex-col rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-navy-700">
          <h3 id="sync-issues-title" className="text-sm font-semibold text-slate-text">Needs your attention</h3>
          <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
        </div>
        <div className="overflow-y-auto divide-y divide-navy-700">
          {failed.map((op) => (
            <div key={op.clientId} className="p-4">
              <p className="text-sm font-medium text-slate-text">{op.label || op.type}</p>
              <p className="text-xs text-slate-dim mb-1">{formatDateTime(op.createdAt)}</p>
              <p className="text-xs text-red-500 dark:text-red-400 mb-3">{op.error || 'The server did not accept this.'}</p>
              <div className="flex gap-2">
                <button onClick={() => retry(op.clientId)} className="btn-ghost flex-1 text-xs">Try again</button>
                <button onClick={() => discard(op.clientId)} className="btn-ghost flex-1 text-xs text-red-500">Discard</button>
              </div>
            </div>
          ))}
        </div>
        <p className="p-3 text-[11px] text-slate-dim border-t border-navy-700">
          Discarding removes it from this device only. If goods were already handed over, record the correction in the app.
        </p>
      </div>
    </div>
  )
}
