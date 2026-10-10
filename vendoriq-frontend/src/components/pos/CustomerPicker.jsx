import { useState, useMemo, useEffect } from 'react'
import { X, Search, UserPlus } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/api'
import { formatCurrency, getErrorMessage } from '../../lib/utils'
import { useOffline } from '../../context/OfflineContext'

/**
 * Pick the customer a sale is for (needed to sell on credit). Works from the
 * cached list, so it works offline; ADDING a new customer needs the server
 * (it has to get a real id), so that is only offered while online.
 */
export default function CustomerPicker({ storeId, customers, onPick, onClose, onCreated }) {
  const { online } = useOffline()
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '' })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? customers.filter((c) => c.name.toLowerCase().includes(q) || (c.phone || '').includes(q)) : customers
  }, [customers, query])

  const create = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { toast.error('Enter the customer\u2019s name'); return }
    setSaving(true)
    try {
      const { data } = await api.post(`/stores/${storeId}/customers/`, { name: form.name, phone: form.phone })
      const c = { id: data.customer.id, name: data.customer.name, phone: data.customer.phone, balance: 0 }
      onCreated?.(c)
      onPick(c)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[55] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Choose customer"
        className="card w-full sm:max-w-sm max-h-[80vh] flex flex-col rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-navy-700">
          <h3 className="text-sm font-semibold text-slate-text">{adding ? 'New customer' : 'Choose customer'}</h3>
          <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
        </div>

        {adding ? (
          <form onSubmit={create} className="p-4 space-y-3">
            <div>
              <label htmlFor="cp-name" className="label">Name</label>
              <input id="cp-name" className="input" autoFocus value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label htmlFor="cp-phone" className="label">Phone <span className="text-slate-dim normal-case">(optional)</span></label>
              <input id="cp-phone" type="tel" className="input" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
            </div>
            <div className="flex gap-3">
              <button type="button" onClick={() => setAdding(false)} className="btn-ghost flex-1">Back</button>
              <button type="submit" disabled={saving} className="btn-primary flex-1">{saving ? 'Saving...' : 'Add & select'}</button>
            </div>
          </form>
        ) : (
          <>
            <div className="p-3 relative">
              <Search size={15} className="absolute left-6 top-1/2 -translate-y-1/2 text-slate-dim" />
              <input className="input pl-9" placeholder="Search name or phone..." value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
            </div>
            <div className="overflow-y-auto divide-y divide-navy-700 flex-1">
              {shown.length === 0 ? (
                <p className="p-4 text-sm text-slate-muted text-center">No customers found</p>
              ) : shown.map((c) => (
                <button key={c.id} onClick={() => onPick(c)} className="w-full px-4 py-3 text-left hover:bg-navy-700/50 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-slate-text truncate">{c.name}</p>
                    {c.phone && <p className="text-xs text-slate-dim">{c.phone}</p>}
                  </div>
                  {c.balance > 0 && <span className="text-xs font-mono text-red-500 dark:text-red-400 flex-shrink-0">owes {formatCurrency(c.balance)}</span>}
                </button>
              ))}
            </div>
            <div className="p-3 border-t border-navy-700">
              <button onClick={() => setAdding(true)} disabled={!online} className="btn-ghost w-full flex items-center justify-center gap-1.5 text-xs disabled:opacity-50">
                <UserPlus size={14} />{online ? 'Add new customer' : 'Go online to add a new customer'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
