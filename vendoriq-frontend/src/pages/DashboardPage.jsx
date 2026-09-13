import { useState, useEffect, useMemo } from 'react'
import { TrendingUp, TrendingDown, Package, AlertTriangle, ShoppingCart, Award, Eye, EyeOff, ChevronDown, Receipt, BarChart3, PackagePlus } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useStore } from '../context/StoreContext'
import { useSubscription } from '../context/SubscriptionContext'
import UpgradePrompt from '../components/billing/UpgradePrompt'
import api from '../lib/api'
import { formatCurrency, formatNumber, formatDateTime, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

function StatCard({ label, value, sub, accent = false, pulse = false, masked = false }) {
  return (
    <div className={`${accent ? 'card-accent' : 'card'} p-4 min-w-0`}>
      <p className="label mb-2">{label}</p>
      <p className={`stat-number text-lg leading-tight break-words font-medium ${pulse ? 'profit-positive' : 'text-slate-text'}`}>
        {masked ? '••••••' : value}
      </p>
      {sub && <p className="text-xs text-slate-dim mt-1">{masked ? 'Hidden' : sub}</p>}
    </div>
  )
}

function Sparkline({ trend }) {
  // Real mini trend line built from actual daily profit figures (the same
  // data backing the Insights page trend chart), not decorative fake points.
  if (!trend || trend.length < 2) {
    return <p className="text-xs text-white/60">Not enough data yet for a trend line</p>
  }
  const values = trend.map(d => Number(d.profit) || 0)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const stepX = 100 / (values.length - 1)
  const coords = values.map((v, i) => [
    Number((i * stepX).toFixed(2)),
    Number((28 - ((v - min) / range) * 26).toFixed(2)),
  ])
  const points = coords.map(([x, y]) => `${x},${y}`).join(' ')
  const [startX, startY] = coords[0]
  const [endX, endY] = coords[coords.length - 1]
  return (
    <svg viewBox="0 0 100 30" className="w-full h-8" preserveAspectRatio="none">
      <title>Net profit over the last {trend.length} days, from {formatCurrency(values[0])} to {formatCurrency(values[values.length - 1])}</title>
      <polyline points={points} fill="none" stroke="white" strokeOpacity="0.85" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={startX} cy={startY} r="1.4" fill="white" fillOpacity="0.6" />
      <circle cx={endX} cy={endY} r="1.6" fill="white" />
    </svg>
  )
}

const PERIODS = [
  { key: 'today', label: 'Today' },
  { key: 'week', label: 'This Week' },
  { key: 'month', label: 'This Month' },
]

const GREETING = () => {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export default function DashboardPage() {
  const { activeStore } = useStore()
  const { isPro } = useSubscription()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [recentSales, setRecentSales] = useState([])
  const [recentExpenses, setRecentExpenses] = useState([])
  const [trend, setTrend] = useState([])
  const [loading, setLoading] = useState(true)
  const [hideProfit, setHideProfit] = useState(() => localStorage.getItem('viq_hide_profit') === 'true')
  const [period, setPeriod] = useState('month')
  const [periodMenuOpen, setPeriodMenuOpen] = useState(false)

  const toggleHideProfit = () => {
    setHideProfit(v => {
      localStorage.setItem('viq_hide_profit', String(!v))
      return !v
    })
  }

  useEffect(() => {
    if (!activeStore) return
    // Same race-condition guard as InsightsPage: switching stores quickly
    // (e.g. via the store switcher) can fire a new fetch before the
    // previous store's request resolves. Without this, whichever response
    // lands LAST wins - so a slower response for the OLD store could
    // overwrite the new store's already-loaded data, silently showing one
    // store's revenue/profit figures while `activeStore` says another.
    let cancelled = false
    const monthStart = new Date()
    monthStart.setDate(1)
    const monthStartStr = monthStart.toISOString().slice(0, 10)

    const fetch = async () => {
      try {
        const [{ data: d }, expensesRes, salesRes, trendRes] = await Promise.all([
          api.get(`/stores/${activeStore.id}/insights/dashboard/`),
          api.get(`/stores/${activeStore.id}/expenses/`, { params: { start: monthStartStr } }).catch(() => null),
          api.get(`/stores/${activeStore.id}/sales/`).catch(() => null),
          api.get(`/stores/${activeStore.id}/insights/trend/`, { params: { days: 14 } }).catch(() => null),
        ])
        if (cancelled) return
        setData(d)
        if (expensesRes) {
          setRecentExpenses(expensesRes.data.expenses.slice(0, 5))
        }
        if (salesRes) setRecentSales(salesRes.data.sales.slice(0, 5))
        if (trendRes) setTrend(trendRes.data.trend)
      } catch (err) {
        if (!cancelled) toast.error(getErrorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetch()
    return () => { cancelled = true }
  }, [activeStore])

  const recentTransactions = useMemo(() => {
    const sales = recentSales.map(s => ({
      id: `sale-${s.id}`, type: 'sale', label: s.recorded_by_name ? `Sale · ${s.recorded_by_name}` : 'Sale',
      amount: s.total_amount, date: s.created_at,
    }))
    const expenses = recentExpenses.map(e => ({
      id: `expense-${e.id}`, type: 'expense', label: `Expense · ${e.description}`,
      amount: e.amount, date: e.incurred_on,
    }))
    return [...sales, ...expenses].sort((a, b) => new Date(b.date) - new Date(a.date)).slice(0, 6)
  }, [recentSales, recentExpenses])

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 bg-navy-800 rounded w-48 animate-pulse" />
        <div className="h-32 bg-navy-800 rounded-2xl animate-pulse" />
        <div className="grid grid-cols-2 gap-3">
          {[1, 2].map(i => <div key={i} className="card p-4 h-20 animate-pulse" />)}
        </div>
      </div>
    )
  }

  if (!data) return null

  const current = data[period]
  const COMPARISON_BASELINE = { today: 'yesterday', week: 'priorWeek', month: 'prevMonthToDate' }
  const COMPARISON_LABEL = { today: 'vs yesterday', week: 'vs last week', month: 'vs same point last month' }
  const baseline = data[COMPARISON_BASELINE[period]]
  const prevNetProfit = Number(baseline?.netProfit || 0)
  const vsBaselinePct = prevNetProfit !== 0
    ? Math.round(((current.netProfit - prevNetProfit) / Math.abs(prevNetProfit)) * 100)
    : (current.netProfit !== 0 ? 100 : null) // baseline was exactly zero - still meaningfully "up" if we made anything at all

  return (
    <div className="p-5 lg:p-6 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-slate-text">{GREETING()}, {activeStore?.name}</h1>
          <p className="text-sm text-slate-dim mt-0.5">
            {new Date().toLocaleDateString('en-NG', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
      </div>

      {/* Period selector */}
      <div className="relative inline-block">
        <button onClick={() => setPeriodMenuOpen(o => !o)} className="flex items-center gap-2 px-3 py-2 bg-navy-800 border border-navy-700 rounded-xl text-sm text-slate-text font-medium">
          {PERIODS.find(p => p.key === period)?.label}
          <ChevronDown size={14} className="text-slate-dim" />
        </button>
        {periodMenuOpen && (
          <div className="absolute left-0 mt-1 w-40 card z-10 overflow-hidden">
            {PERIODS.map(p => (
              <button key={p.key} onClick={() => { setPeriod(p.key); setPeriodMenuOpen(false) }}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-navy-700 transition-colors ${p.key === period ? 'text-brand-500 font-medium' : 'text-slate-text'}`}>
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Profit hero card */}
      <div className="card-hero p-5">
        <p className="text-sm text-white/80 mb-1">Net Profit</p>
        <div className="flex items-center gap-2 mb-1">
          <p className="text-3xl font-bold font-mono tabular-nums">
            {hideProfit ? '••••••' : formatCurrency(current.netProfit)}
          </p>
          <button onClick={toggleHideProfit} className="text-white/70 hover:text-white transition-colors p-1 flex-shrink-0" title={hideProfit ? 'Show profit figures' : 'Hide profit figures'}>
            {hideProfit ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        <p className="text-xs text-white/60 mb-2">
          {hideProfit ? '••••' : formatCurrency(current.salesProfit)} sales profit − {hideProfit ? '••••' : formatCurrency(current.expenses)} expenses
        </p>
        {vsBaselinePct !== null && (
          <p className="text-xs text-white/80 flex items-center gap-1 mb-3">
            {vsBaselinePct >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
            {Math.abs(vsBaselinePct)}% {COMPARISON_LABEL[period]}
          </p>
        )}
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-[11px] text-white/50">Net profit trend, last {trend.length || 14} days</p>
          {trend.length >= 2 && (
            <p className="text-[11px] text-white/50 font-mono">
              {formatCurrency(trend[0]?.profit)} → {formatCurrency(trend[trend.length - 1]?.profit)}
            </p>
          )}
        </div>
        <Sparkline trend={trend} />
      </div>

      {/* Total sales / expenses */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card p-4 min-w-0">
          <p className="label mb-1">Total Sales</p>
          <p className="stat-number text-lg font-semibold leading-tight break-words">{formatCurrency(current.revenue)}</p>
          <p className="text-xs text-slate-dim mt-1">{current.transactions} transactions</p>
        </div>
        <div className="card p-4 min-w-0">
          <p className="label mb-1">Total Expenses</p>
          <p className="stat-number text-lg font-semibold leading-tight break-words">{formatCurrency(current.expenses)}</p>
          <p className="text-xs text-slate-dim mt-1">{PERIODS.find(p => p.key === period)?.label}</p>
        </div>
      </div>

      {/* Quick actions */}
      <section>
        <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">Quick Actions</p>
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'Add Sale', icon: ShoppingCart, color: 'bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400', to: '/sales' },
            { label: 'Add Expense', icon: Receipt, color: 'bg-red-50 text-red-500 dark:bg-red-500/15 dark:text-red-400', to: '/expenses' },
            { label: 'View Reports', icon: BarChart3, color: 'bg-blue-50 text-blue-500 dark:bg-blue-500/15 dark:text-blue-400', to: '/insights' },
            { label: 'Manage Products', icon: PackagePlus, color: 'bg-purple-50 text-purple-500 dark:bg-purple-500/15 dark:text-purple-400', to: '/products' },
          ].map(action => (
            <button key={action.label} onClick={() => navigate(action.to)} className="card p-3 flex flex-col items-center gap-2 text-center hover:border-brand-500/40 transition-colors">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center ${action.color}`}>
                <action.icon size={17} />
              </div>
              <span className="text-[11px] font-medium text-slate-muted leading-tight">{action.label}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Recent transactions */}
      {recentTransactions.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest">Recent Transactions</p>
            <button onClick={() => navigate('/transactions')} className="text-xs text-brand-500 font-medium">View all</button>
          </div>
          <div className="card divide-y divide-navy-700">
            {recentTransactions.map(tx => (
              <div key={tx.id} className="flex items-center gap-3 px-4 py-3 min-w-0">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${tx.type === 'sale' ? 'bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400' : 'bg-red-50 text-red-500 dark:bg-red-500/15 dark:text-red-400'}`}>
                  {tx.type === 'sale' ? <ShoppingCart size={14} /> : <Receipt size={14} />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-text truncate">{tx.label}</p>
                  <p className="text-xs text-slate-dim truncate">{formatDateTime(tx.date)}</p>
                </div>
                <p className={`font-mono text-sm flex-shrink-0 whitespace-nowrap ${tx.type === 'sale' ? 'text-slate-text' : 'text-red-500 dark:text-red-400'}`}>
                  {tx.type === 'sale' ? '' : '-'}{formatCurrency(tx.amount)}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Inventory summary */}
      <section>
        <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">Inventory</p>
        <div className="grid grid-cols-2 gap-3">
          <StatCard label="Stock value" value={formatCurrency(data.inventory.totalStockValue)} sub="At cost price" />
          <StatCard label="Retail value" value={formatCurrency(data.inventory.totalRetailValue)} sub={`${formatNumber(data.inventory.totalProducts)} products`} />
        </div>
      </section>

      {/* Low stock alerts */}
      {data.lowStockProducts?.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-amber-500" />
            <p className="text-xs font-semibold text-amber-600 dark:text-amber-400 uppercase tracking-widest">Low stock</p>
          </div>
          <div className="card divide-y divide-navy-700">
            {data.lowStockProducts.map(p => (
              <div key={p.id} className="flex items-center justify-between px-4 py-3">
                <span className="text-sm text-slate-text">{p.name}</span>
                <span className={`font-mono text-sm ${p.quantity === 0 ? 'text-red-500 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'}`}>
                  {p.quantity} left
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Best sellers */}
      {data.bestSellers?.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Award size={14} className="text-brand-500" />
            <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest">Best sellers this month</p>
          </div>
          <div className="card divide-y divide-navy-700">
            {data.bestSellers.map((b, i) => (
              <div key={b.productId} className="flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-xs text-slate-dim w-4">{i + 1}</span>
                  <span className="text-sm text-slate-text">{b.product?.name}</span>
                </div>
                <span className="font-mono text-sm text-brand-500">{formatNumber(b._sum.quantity)} sold</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Dead stock */}
      {data.deadStock?.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Package size={14} className="text-slate-dim" />
            <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest">Not moving</p>
          </div>
          <div className="card divide-y divide-navy-700">
            {data.deadStock.map(p => (
              <div key={p.id} className="flex items-center justify-between px-4 py-3">
                <span className="text-sm text-slate-text">{p.name}</span>
                <span className="font-mono text-xs text-slate-dim">{p.quantity} in stock</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Tasteful Pro upsell - only for Free plan, and only ever added
          content (never hides anything a Free user already had access to). */}
      {!isPro && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 size={14} className="text-slate-dim" />
            <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest">See more with Pro</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <UpgradePrompt feature="ai_assistant" compact />
            <UpgradePrompt feature="detailed_reports" compact />
          </div>
        </section>
      )}
    </div>
  )
}
