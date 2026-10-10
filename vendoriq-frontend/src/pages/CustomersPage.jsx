import { useState, useEffect, useCallback, useMemo } from 'react'
import { Plus, Search, Users, X, Phone, WifiOff } from 'lucide-react'
import toast from 'react-hot-toast'
import { useStore } from '../context/StoreContext'
import { useAuth } from '../context/AuthContext'
import { useOffline } from '../context/OfflineContext'
import { useCatalog } from '../hooks/useCatalog'
import { useSubscription } from '../context/SubscriptionContext'
import UpgradePrompt from '../components/billing/UpgradePrompt'
import api from '../lib/api'
import { submitCustomerPayment } from '../lib/offline/sales'
import { METHODS, parseMoney, methodLabel } from '../lib/offline/money'
import { formatCurrency, formatDateTime, getErrorMessage } from '../lib/utils'

function CustomerSheet({ customer, onClose, onChanged }) {
  const { activeStore } = useStore()
  const { user } = useAuth()
  const { online } = useOffline()
  const [statement, setStatement] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('CASH')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/customers/${customer.id}/statement/`)
      setStatement(data)
      setLoadError('')
    } catch (err) {
      setLoadError(online ? getErrorMessage(err) : "You're offline - the history appears when you reconnect.")
    }
  }, [activeStore.id, customer.id, online])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const owed = statement?.customer.balance ?? customer.balance
  const value = parseMoney(amount)

  const receive = async (e) => {
    e.preventDefault()
    if (!(value > 0) || Number.isNaN(value)) { toast.error('Enter the amount received'); return }
    if (value > owed + 0.001) { toast.error(`They only owe ${formatCurrency(owed)}`); return }
    setSaving(true)
    try {
      const result = await submitCustomerPayment({ store: activeStore, user, customer, amount: value, method })
      toast.success(result.status === 'queued' ? 'Saved offline - will sync automatically' : 'Payment recorded')
      setAmount('')
      onChanged()
      if (result.status === 'synced') load()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={customer.name}
        className="card w-full sm:max-w-md max-h-[90vh] flex flex-col rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between p-4 border-b border-navy-700">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-slate-text truncate">{customer.name}</h3>
            {customer.phone && <p className="text-xs text-slate-dim flex items-center gap-1"><Phone size={11} />{customer.phone}</p>}
          </div>
          <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
        </div>

        <div className="overflow-y-auto p-4 space-y-4">
          <div className="rounded-xl bg-navy-700/40 p-4 text-center">
            <p className="label mb-1">Owes</p>
            <p className={`text-3xl font-bold font-mono ${owed > 0 ? 'text-red-500 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}>{formatCurrency(owed)}</p>
          </div>

          {owed > 0 && (
            <form onSubmit={receive} className="space-y-3">
              <p className="text-sm font-semibold text-slate-text">Receive a payment</p>
              <div className="flex gap-2">
                <input className="input font-mono flex-1" inputMode="decimal" placeholder="Amount" aria-label="Amount received" value={amount}
                  onChange={(e) => setAmount(e.target.value.replace(/[^0-9.,]/g, ''))} />
                <select className="input w-32" aria-label="Paid by" value={method} onChange={(e) => setMethod(e.target.value)}>
                  {METHODS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => setAmount(String(owed))} className="btn-ghost text-xs flex-1">Pay in full</button>
                <button type="submit" disabled={saving} className="btn-primary flex-1">{saving ? 'Saving...' : 'Record payment'}</button>
              </div>
              {!online && <p className="text-[11px] text-slate-dim">Offline - the payment is saved on this device and synced later.</p>}
            </form>
          )}

          {loadError ? (
            <p className="flex items-center gap-2 text-xs text-slate-dim"><WifiOff size={13} />{loadError}</p>
          ) : !statement ? (
            <div className="card h-20 animate-pulse" />
          ) : (
            <>
              <div>
                <p className="label mb-2">Purchases</p>
                {statement.sales.length === 0 ? <p className="text-xs text-slate-dim">No purchases yet.</p> : (
                  <div className="card divide-y divide-navy-700">
                    {statement.sales.map((s) => (
                      <div key={s.id} className="px-3 py-2 flex justify-between gap-3 text-sm">
                        <div className="min-w-0">
                          <p className="text-slate-text truncate">{formatDateTime(s.created_at)} <span className="text-xs text-slate-dim font-mono">#{s.receipt_no}</span></p>
                          <p className="text-xs text-slate-dim">Total {formatCurrency(s.total_amount)} · paid {formatCurrency(s.amount_paid)}</p>
                        </div>
                        {s.balance_due > 0 && <span className="text-xs font-mono text-red-500 dark:text-red-400 flex-shrink-0">owes {formatCurrency(s.balance_due)}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {statement.payments.length > 0 && (
                <div>
                  <p className="label mb-2">Payments received</p>
                  <div className="card divide-y divide-navy-700">
                    {statement.payments.map((p) => (
                      <div key={p.id} className="px-3 py-2 flex justify-between gap-3 text-sm">
                        <span className="text-slate-text">{formatDateTime(p.created_at)} <span className="text-xs text-slate-dim">· {methodLabel(p.method)}</span></span>
                        <span className="font-mono text-green-600 dark:text-green-400">{formatCurrency(p.amount)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function CustomersPage() {
  const { activeStore } = useStore()
  const { online } = useOffline()
  const { hasFeature } = useSubscription()
  const { catalog, loaded, reload } = useCatalog(activeStore?.id)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '' })
  const [saving, setSaving] = useState(false)

  // The customer list comes from the offline catalog, so it also works with no connection.
  // The catalog carries the SERVER's verdict on the plan; until it has arrived
  // we don't know, and showing an upgrade prompt to a Pro user would be wrong.
  const allowed = catalog ? catalog.customersEnabled : hasFeature('customer_management')
  const customers = catalog?.customers || []

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? customers.filter((c) => c.name.toLowerCase().includes(q) || (c.phone || '').includes(q)) : customers
  }, [customers, query])
  const totalOwed = customers.reduce((sum, c) => sum + Math.max(0, c.balance), 0)
  const debtors = customers.filter((c) => c.balance > 0).length

  const create = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { toast.error('Enter the customer\u2019s name'); return }
    setSaving(true)
    try {
      await api.post(`/stores/${activeStore.id}/customers/`, { name: form.name, phone: form.phone })
      toast.success('Customer added')
      setForm({ name: '', phone: '' })
      setAdding(false)
      reload()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (loaded && catalog && !allowed) {
    return (
      <div className="p-5 lg:p-6 animate-fade-in">
        <h1 className="text-xl font-bold text-slate-text mb-5">Customers</h1>
        <UpgradePrompt feature="customer_management" />
      </div>
    )
  }

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Customers</h1>
        <button onClick={() => setAdding(true)} disabled={!online} aria-label="Add customer" title={online ? 'Add customer' : 'Go online to add customers'}
          className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center hover:bg-brand-600 transition-colors disabled:opacity-40">
          <Plus size={18} />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-5">
        <div className="card p-3"><p className="label mb-1">Total owed to you</p><p className="stat-number text-sm text-red-500 dark:text-red-400">{formatCurrency(totalOwed)}</p></div>
        <div className="card p-3"><p className="label mb-1">Customers owing</p><p className="stat-number text-sm">{debtors}</p></div>
      </div>

      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-dim" />
        <input className="input pl-9" placeholder="Search name or phone..." value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      {!loaded ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="card h-14 animate-pulse" />)}</div>
      ) : shown.length === 0 ? (
        <div className="card p-10 text-center">
          <Users size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-sm text-slate-muted">{customers.length === 0 ? 'No customers yet. Add the people you sell to on credit.' : 'No customers match your search.'}</p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {[...shown].sort((a, b) => b.balance - a.balance || a.name.localeCompare(b.name)).map((c) => (
            <button key={c.id} onClick={() => setOpen(c)} className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-navy-700/50 transition-colors">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-text truncate">{c.name}</p>
                {c.phone && <p className="text-xs text-slate-dim">{c.phone}</p>}
              </div>
              {c.balance > 0
                ? <span className="text-sm font-mono text-red-500 dark:text-red-400 flex-shrink-0">{formatCurrency(c.balance)}</span>
                : <span className="text-xs text-slate-dim flex-shrink-0">settled</span>}
            </button>
          ))}
        </div>
      )}

      {open && <CustomerSheet customer={open} onClose={() => setOpen(null)} onChanged={reload} />}

      {adding && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => setAdding(false)}>
          <div role="dialog" aria-modal="true" aria-label="Add customer" className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-slate-text mb-4">Add customer</h3>
            <form onSubmit={create} className="space-y-3">
              <div>
                <label htmlFor="cust-name" className="label">Name</label>
                <input id="cust-name" className="input" autoFocus value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div>
                <label htmlFor="cust-phone" className="label">Phone <span className="text-slate-dim normal-case">(optional)</span></label>
                <input id="cust-phone" type="tel" className="input" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
              </div>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setAdding(false)} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={saving} className="btn-primary flex-1">{saving ? 'Saving...' : 'Add customer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
