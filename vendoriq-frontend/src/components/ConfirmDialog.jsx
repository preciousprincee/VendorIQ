import { useEffect, useRef } from 'react'
import { AlertTriangle } from 'lucide-react'

/**
 * In-app replacement for window.confirm(). Browser confirm() popups look
 * broken/untrustworthy in a mobile webview, can't be styled, and silently
 * block the whole page. This renders inline instead.
 *
 * Usage: keep a piece of state holding the thing pending deletion (or null),
 * pass `open={!!pendingThing}`, and call onConfirm/onCancel to clear it.
 *
 * Accessibility: focus moves to Cancel on open (the safer of the two
 * actions, and the same target Escape triggers) so keyboard/screen-reader
 * users land somewhere immediately instead of on whatever was behind the
 * dialog; Escape closes it the same as clicking the backdrop.
 */
export default function ConfirmDialog({
  open,
  title = 'Are you sure?',
  message,
  confirmLabel = 'Delete',
  cancelLabel = 'Cancel',
  danger = true,
  loading = false,
  onConfirm,
  onCancel,
}) {
  const cancelRef = useRef(null)

  useEffect(() => {
    if (!open) return
    cancelRef.current?.focus()
    const onKeyDown = (e) => { if (e.key === 'Escape') onCancel() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onCancel}>
      <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
        <div className="flex items-start gap-3 mb-4">
          {danger && (
            <div className="w-9 h-9 rounded-full bg-red-50 dark:bg-red-500/15 flex items-center justify-center flex-shrink-0">
              <AlertTriangle size={17} className="text-red-500 dark:text-red-400" aria-hidden="true" />
            </div>
          )}
          <div className="min-w-0">
            <h3 id="confirm-dialog-title" className="text-sm font-semibold text-slate-text">{title}</h3>
            {message && <p className="text-sm text-slate-dim mt-1">{message}</p>}
          </div>
        </div>
        <div className="flex gap-3">
          <button ref={cancelRef} type="button" onClick={onCancel} disabled={loading} className="btn-ghost flex-1">{cancelLabel}</button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`flex-1 font-semibold px-4 py-2.5 rounded-xl shadow-sm text-sm text-white ${danger ? 'bg-red-500 hover:bg-red-600' : 'bg-brand-500'}`}
          >
            {loading ? 'Working...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
