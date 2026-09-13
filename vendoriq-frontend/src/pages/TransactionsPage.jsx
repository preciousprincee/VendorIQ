import { useState, useEffect, useMemo } from 'react'
import { ShoppingCart, Receipt, ListFilter } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import api from '../lib/api'
import { formatCurrency, formatDateTime, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'sale', label: 'Sales' },
  { key: 'expense', label: 'Expenses' },
]

export default function TransactionsPage() {
  const { activeStore } = useStore()
  const [sales, setSales] = useState([])
  const [expenses, setExpenses] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    if (!activeStore) return
    // Same race guard as Dashboard/Insights - switching stores quickly
    // could let a slower response for the OLD store land after the new
    // store's data has already loaded, silently overwriting it.
    let cancelled = false
    const fetch = async () => {
      setLoading(true)
      try {
        const [salesRes, expensesRes] = await Promise.all([
          api.get(`/stores/${activeStore.id}/sales/`).catch(() => null),
          api.get(`/stores/${activeStore.id}/expenses/`).catch(() => null),
        ])
        if (cancelled) return
        if (salesRes) setSales(salesRes.data.sales || [])
        if (expensesRes) setExpenses(expensesRes.data.expenses || [])
      } catch (err) {
        if (!cancelled) toast.error(getErrorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetch()
    return () => { cancelled = true }
  }, [activeStore])

  const transactions = useMemo(() => {
    const saleTx = sales.map(s => ({
      id: `sale-${s.id}`,
      type: 'sale',
      label: s.recorded_by_name ? `Sale · ${s.recorded_by_name}` : 'Sale',
      detail: (s.sale_items ?? []).map(i => `${i.product?.name || 'Unknown'} ×${i.quantity}`).join(', '),
      amount: s.total_amount,
      date: s.created_at,
    }))
    const expenseTx = expenses.map(e => ({
      id: `expense-${e.id}`,
      type: 'expense',
      label: `Expense · ${e.description}`,
      detail: e.category,
      amount: e.amount,
      date: e.incurred_on,
    }))
    return [...saleTx, ...expenseTx].sort((a, b) => new Date(b.date) - new Date(a.date))
  }, [sales, expenses])

  const filtered = filter === 'all' ? transactions : transactions.filter(t => t.type === filter)

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Transactions</h1>
      </div>

      <div className="flex items-center gap-2 mb-4">
        <ListFilter size={14} className="text-slate-dim flex-shrink-0" />
        {FILTERS.map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${filter === f.key ? 'bg-brand-500 text-white' : 'bg-navy-800 text-slate-dim hover:text-slate-text'}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map(i => <div key={i} className="card h-16 animate-pulse" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="card p-10 text-center">
          <Receipt size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">No transactions to show.</p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {filtered.map(tx => (
            <div key={tx.id} className="flex items-center gap-3 px-4 py-3 min-w-0">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 ${tx.type === 'sale' ? 'bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400' : 'bg-red-50 text-red-500 dark:bg-red-500/15 dark:text-red-400'}`}>
                {tx.type === 'sale' ? <ShoppingCart size={15} /> : <Receipt size={15} />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-text truncate">{tx.label}</p>
                {tx.detail && <p className="text-xs text-slate-dim truncate">{tx.detail}</p>}
                <p className="text-xs text-slate-dim/70 truncate">{formatDateTime(tx.date)}</p>
              </div>
              <p className={`font-mono text-sm flex-shrink-0 whitespace-nowrap ${tx.type === 'sale' ? 'text-slate-text' : 'text-red-500 dark:text-red-400'}`}>
                {tx.type === 'sale' ? '' : '-'}{formatCurrency(tx.amount)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
