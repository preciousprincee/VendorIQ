import { useEffect, useRef } from 'react'

/**
 * In-app confirmation dialog, styled to match the rest of VendorIQ instead
 * of the browser's native window.confirm() - which looks like an
 * out-of-place OS-level prompt and can't carry a "keep your data" reminder
 * or any styling at all. Used for the subscription cancel flow
 * specifically (see SubscriptionPage) since cancelling billing is a
 * higher-stakes action worth a proper in-app moment, not a one-line
 * browser popup.
 */
export default function ConfirmDialog({ open, title, description, confirmLabel = 'Confirm', cancelLabel = 'Never mind', danger = false, working = false, onConfirm, onCancel }) {
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
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 animate-fade-in" onClick={onCancel}>
      <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-ui-title" className="card w-full sm:max-w-sm rounded-b-none sm:rounded-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="p-5">
          <p id="confirm-dialog-ui-title" className="text-sm font-semibold text-slate-text mb-1.5">{title}</p>
          {description && <p className="text-xs text-slate-dim leading-relaxed mb-5">{description}</p>}
          <div className="flex gap-2">
            <button ref={cancelRef} onClick={onCancel} disabled={working} className="btn-ghost flex-1 text-sm">
              {cancelLabel}
            </button>
            <button
              onClick={onConfirm}
              disabled={working}
              className={`flex-1 text-sm rounded-xl font-semibold py-2.5 transition-colors ${
                danger
                  ? 'bg-red-500 text-white hover:bg-red-600'
                  : 'btn-primary'
              }`}
            >
              {working ? 'Working\u2026' : confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
