import { useState, useEffect, useRef } from 'react'
import { Plus, X, Trash2, Wallet, TrendingDown, TrendingUp } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import api from '../lib/api'
import { formatCurrency, formatDate, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'
import UpgradePrompt from '../components/billing/UpgradePrompt'
import ConfirmDialog from '../components/ConfirmDialog'

const CATEGORIES = [
  { value: 'RENT', label: 'Rent' },
  { value: 'UTILITIES', label: 'Utilities' },
  { value: 'SALARIES', label: 'Salaries' },
  { value: 'TRANSPORT', label: 'Transport' },
  { value: 'PACKAGING', label: 'Packaging' },
  { value: 'MAINTENANCE', label: 'Maintenance' },
  { value: 'MISCELLANEOUS', label: 'Miscellaneous' },
  { value: 'OTHER', label: 'Other' },
]

const OVERHEAD_CATEGORIES = ['RENT', 'UTILITIES', 'SALARIES']

const EMPTY_FORM = {
  category: 'MISCELLANEOUS',
  description: '',
  amount: '',
  frequency: 'ONE_OFF',
  is_overhead: false,
  incurred_on: new Date().toISOString().slice(0, 10),
}

export default function ExpensesPage() {
  const { activeStore } = useStore()
  const [expenses, setExpenses] = useState([])
  const [summary, setSummary] = useState(null)
  const [profitability, setProfitability] = useState(null)
  const [profitLocked, setProfitLocked] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const fetchDataRef = useRef(0)
  const [showForm, setShowForm] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)

  const fetchData = async () => {
    // Same request-counter guard as ProductsPage/SalesPage/StaffPage/
    // InvoicesPage - switching stores quickly could let a slower response
    // for the OLD store land after the new store's data has already
    // loaded, silently overwriting it (including setProfitLocked, which
    // would otherwise show a stale upgrade-prompt state for the wrong
    // store's plan).
    const requestId = ++fetchDataRef.current
    try {
      const [expensesRes, profitRes] = await Promise.all([
        api.get(`/stores/${activeStore.id}/expenses/`),
        // skipUpgradeModal: this is a passive load-time fetch, not an
        // explicit click - a locked plan should render an inline
        // <UpgradePrompt> below, not pop the upgrade modal unprompted.
        api.get(`/stores/${activeStore.id}/profitability/`, { skipUpgradeModal: true }).catch((err) => {
          // 402 = Free plan (owner, but plan doesn't include this) - show
          // the upgrade prompt. 403 = not the owner at all (manager) -
          // this section simply isn't for them, same as before.
          if (err.response?.status === 402 && requestId === fetchDataRef.current) setProfitLocked(true)
          return null
        }),
      ])
      if (requestId !== fetchDataRef.current) return
      setExpenses(expensesRes.data.expenses)
      setSummary(expensesRes.data.summary)
      if (profitRes) setProfitability(profitRes.data)
    } catch (err) {
      if (requestId === fetchDataRef.current) toast.error(getErrorMessage(err))
    } finally {
      if (requestId === fetchDataRef.current) setLoading(false)
    }
  }

  useEffect(() => { if (activeStore) fetchData() }, [activeStore])

  const set = (k) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm(f => {
      const next = { ...f, [k]: value }
      // Default is_overhead based on category, but let the user override it.
      if (k === 'category') next.is_overhead = OVERHEAD_CATEGORIES.includes(value)
      return next
    })
  }

  const handleAdd = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post(`/stores/${activeStore.id}/expenses/`, {
        ...form,
        amount: Number(form.amount),
      })
      toast.success('Expense recorded')
      setShowForm(false)
      setForm(EMPTY_FORM)
      fetchData()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = (expense) => {
    setPendingDelete(expense)
  }

  const confirmDelete = async () => {
    const expense = pendingDelete
    setDeleting(true)
    try {
      await api.delete(`/stores/${activeStore.id}/expenses/${expense.id}/`)
      toast.success('Expense deleted')
      fetchData()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  if (showForm) return (
    <div className="p-5 max-w-lg">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => setShowForm(false)} className="text-slate-muted hover:text-slate-text"><X size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">Add expense</h1>
      </div>
      <form onSubmit={handleAdd} className="space-y-4">
        <div>
          <label htmlFor="exp-desc" className="label">Description</label>
          <input id="exp-desc" className="input" placeholder="e.g. Shop rent for July" value={form.description} onChange={set('description')} required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="exp-category" className="label">Category</label>
            <select id="exp-category" className="input" value={form.category} onChange={set('category')}>
              {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="exp-amount" className="label">Amount (₦)</label>
            <input id="exp-amount" type="number" className="input font-mono" placeholder="0" min="0.01" step="0.01"
              value={form.amount} onChange={set('amount')} required />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="exp-date" className="label">Date incurred</label>
            <input id="exp-date" type="date" className="input" value={form.incurred_on} onChange={set('incurred_on')} required />
          </div>
          <div>
            <label htmlFor="exp-frequency" className="label">Frequency</label>
            <select id="exp-frequency" className="input" value={form.frequency} onChange={set('frequency')}>
              <option value="ONE_OFF">One-off</option>
              <option value="DAILY">Daily</option>
              <option value="WEEKLY">Weekly</option>
              <option value="MONTHLY">Monthly</option>
              <option value="YEARLY">Yearly</option>
            </select>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-muted">
          <input type="checkbox" checked={form.is_overhead} onChange={set('is_overhead')} className="rounded" />
          This is a recurring overhead cost (rent, salaries, utilities), not a one-off misc expense
        </label>
        <div className="flex gap-3 pt-2">
          <button type="submit" disabled={saving} className="btn-primary flex-1">
            {saving ? 'Saving...' : 'Save expense'}
          </button>
          <button type="button" onClick={() => setShowForm(false)} className="btn-ghost">Cancel</button>
        </div>
      </form>
    </div>
  )

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Expenses</h1>
        <button onClick={() => setShowForm(true)} className="btn-primary flex items-center gap-2 text-sm">
          <Plus size={16} />Add expense
        </button>
      </div>

      {profitability && (
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div className="card p-3 min-w-0">
            <p className="label mb-1">This month sales profit</p>
            <p className="stat-number text-base leading-tight break-words">{formatCurrency(profitability.month.salesProfit)}</p>
          </div>
          <div className="card p-3 min-w-0">
            <p className="label mb-1">This month expenses</p>
            <p className="stat-number text-base leading-tight break-words text-red-500 dark:text-red-400">{formatCurrency(profitability.month.expenses)}</p>
          </div>
          <div className="card-accent p-3 col-span-2 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              {profitability.month.netProfit >= 0
                ? <TrendingUp size={14} className="text-brand-500" />
                : <TrendingDown size={14} className="text-red-500 dark:text-red-400" />}
              <p className="label">This month's true net profit</p>
            </div>
            <p className={`stat-number text-lg leading-tight break-words ${profitability.month.netProfit >= 0 ? 'text-brand-500' : 'text-red-500 dark:text-red-400'}`}>
              {formatCurrency(profitability.month.netProfit)}
            </p>
            <p className="text-xs text-slate-dim mt-1">Sales profit minus misc expenses and overhead costs</p>
          </div>
        </div>
      )}

      {profitLocked && (
        <div className="mb-5">
          <UpgradePrompt feature="advanced_profit_analytics" />
        </div>
      )}

      {summary && (
        <div className="flex gap-4 mb-4 text-xs text-slate-muted">
          <span>Overhead: <span className="font-mono text-slate-text">{formatCurrency(summary.overheadTotal)}</span></span>
          <span>Misc: <span className="font-mono text-slate-text">{formatCurrency(summary.miscTotal)}</span></span>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="card h-16 animate-pulse" />)}</div>
      ) : expenses.length === 0 ? (
        <div className="card p-10 text-center">
          <Wallet size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">No expenses recorded yet. Add rent, salaries, or other costs to see your true profit.</p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {expenses.map(expense => (
            <div key={expense.id} className="px-4 py-3 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-slate-text truncate">{expense.description}</p>
                  <span className={`badge ${expense.is_overhead ? 'badge-warning' : 'badge-success'} flex-shrink-0`}>
                    {expense.is_overhead ? 'Overhead' : 'Misc'}
                  </span>
                </div>
                <p className="text-xs text-slate-dim mt-0.5">{formatDate(expense.incurred_on)} · {CATEGORIES.find(c => c.value === expense.category)?.label}</p>
              </div>
              <p className="font-mono text-sm text-slate-text flex-shrink-0">{formatCurrency(expense.amount)}</p>
              <button onClick={() => handleDelete(expense)} className="p-2 text-slate-dim hover:text-red-500 dark:hover:text-red-400 transition-colors flex-shrink-0">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!pendingDelete}
        title={`Delete "${pendingDelete?.description}"?`}
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
