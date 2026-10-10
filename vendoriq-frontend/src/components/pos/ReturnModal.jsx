import { useState, useMemo, useEffect } from 'react'
import { X, Minus, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { METHODS, previewReturn } from '../../lib/offline/money'
import { formatCurrency, getErrorMessage } from '../../lib/utils'
import { useOffline } from '../../context/OfflineContext'

/**
 * Take goods back from a sale. The refund shown is a PREVIEW using the same
 * maths as the server (which has the final say): the discount is shared
 * across the returned lines, money only goes back for what was actually
 * paid, and goods from an unpaid credit sale just reduce what is owed.
 */
export default function ReturnModal({ storeId, sale, onClose, onDone }) {
  const { online } = useOffline()
  const [picks, setPicks] = useState({})
  const [method, setMethod] = useState('CASH')
  const [restock, setRestock] = useState(true)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const items = sale.sale_items
  const remaining = (i) => i.quantity - (i.returned_quantity || 0)
  const chosen = Object.values(picks).reduce((a, b) => a + b, 0)
  const preview = useMemo(() => previewReturn(sale, picks), [sale, picks])

  const step = (item, delta) => {
    setPicks((p) => {
      const next = Math.max(0, Math.min(remaining(item), (p[item.id] || 0) + delta))
      return { ...p, [item.id]: next }
    })
  }

  const submit = async () => {
    if (chosen === 0) { toast.error('Choose at least one item to return'); return }
    setSaving(true)
    try {
      const { data } = await api.post(`/stores/${storeId}/sales/${sale.id}/returns/`, {
        items: Object.entries(picks).filter(([, q]) => q > 0).map(([saleItemId, quantity]) => ({ saleItemId, quantity })),
        refundMethod: preview.refund > 0 ? method : '',
        restock,
        reason: reason.trim(),
      })
      toast.success(data.refundAmount > 0 ? `Return recorded - give back ${formatCurrency(data.refundAmount)}` : 'Return recorded')
      onDone(data.sale)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Return items"
        className="card w-full sm:max-w-sm max-h-[92vh] overflow-y-auto p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-text">Return items</h3>
          <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
        </div>

        <div className="card divide-y divide-navy-700 mb-4">
          {items.map((item) => (
            <div key={item.id} className="px-3 py-2.5 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-text truncate">{item.product?.name}</p>
                <p className="text-xs text-slate-dim font-mono">{formatCurrency(item.unit_price)} · {remaining(item)} left to return</p>
              </div>
              {remaining(item) > 0 ? (
                <div className="flex items-center gap-2">
                  <button onClick={() => step(item, -1)} aria-label="Fewer" className="w-7 h-7 rounded-full bg-navy-700 flex items-center justify-center"><Minus size={13} /></button>
                  <span className="font-mono text-sm w-5 text-center">{picks[item.id] || 0}</span>
                  <button onClick={() => step(item, 1)} aria-label="More" className="w-7 h-7 rounded-full bg-navy-700 flex items-center justify-center"><Plus size={13} /></button>
                </div>
              ) : <span className="text-xs text-slate-dim">all returned</span>}
            </div>
          ))}
        </div>

        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm text-slate-text">
            <input type="checkbox" checked={restock} onChange={(e) => setRestock(e.target.checked)} />
            Put the goods back in stock
          </label>
          <div>
            <label htmlFor="ret-reason" className="label">Reason <span className="text-slate-dim normal-case">(optional)</span></label>
            <input id="ret-reason" className="input" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. damaged, wrong size" />
          </div>
        </div>

        <div className="mt-4 rounded-xl bg-navy-700/40 p-3 space-y-1 text-sm">
          <div className="flex justify-between"><span className="text-slate-muted">Value of goods returned</span><span className="font-mono">{formatCurrency(preview.value)}</span></div>
          <div className="flex justify-between font-semibold">
            <span className="text-slate-text">Refund to give back</span>
            <span className={`font-mono ${preview.refund > 0 ? 'text-amber-600 dark:text-amber-400' : ''}`}>{formatCurrency(preview.refund)}</span>
          </div>
          {preview.value > 0 && preview.refund === 0 && <p className="text-xs text-slate-dim">Nothing was paid for these items, so this just reduces what the customer owes.</p>}
        </div>

        {preview.refund > 0 && (
          <div className="mt-3">
            <label htmlFor="ret-method" className="label">Refund paid by</label>
            <select id="ret-method" className="input" value={method} onChange={(e) => setMethod(e.target.value)}>
              {METHODS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
        )}

        {!online && <p className="text-xs text-amber-600 dark:text-amber-400 mt-3">Returns need an internet connection. Try again when you're online.</p>}
        <div className="flex gap-3 mt-4">
          <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          <button onClick={submit} disabled={saving || chosen === 0 || !online} className="btn-primary flex-1">{saving ? 'Saving...' : 'Record return'}</button>
        </div>
      </div>
    </div>
  )
}
