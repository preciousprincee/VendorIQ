import { useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Download } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useTheme } from '../context/ThemeContext'
import { useSubscription } from '../context/SubscriptionContext'
import { useFeatureAccess } from '../hooks/useFeatureAccess'
import api from '../lib/api'
import { formatCurrency, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-navy-800 border border-navy-600 rounded-lg px-3 py-2 text-xs shadow-md">
      <p className="text-slate-muted mb-1">{label}</p>
      <p className="text-brand-500 font-mono">Net profit: {formatCurrency(payload[0]?.value)}</p>
      <p className="text-slate-text font-mono">Revenue: {formatCurrency(payload[1]?.value)}</p>
    </div>
  )
}

export default function InsightsPage() {
  const { activeStore } = useStore()
  const { theme } = useTheme()
  const { limits, openUpgradeModal } = useSubscription()
  const { requireAccess: requireExport } = useFeatureAccess('data_export')
  const maxHistoryDays = limits?.maxTrendHistoryDays ?? 365
  // Recharts needs literal color values, not Tailwind classes, so these mirror
  // the brand-500/400 and slate-muted tokens for each mode.
  const profitColor = theme === 'dark' ? '#3DB57C' : '#1E8449'
  const revenueColor = theme === 'dark' ? '#8CA396' : '#6B7268'
  const axisColor = theme === 'dark' ? '#8CA396' : '#9CA396'
  const [trend, setTrend] = useState([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)

  const handleExport = async () => {
    if (!requireExport()) return
    setExporting(true)
    try {
      const response = await api.get(`/stores/${activeStore.id}/export/`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      const disposition = response.headers['content-disposition']
      const match = disposition?.match(/filename="?([^"]+)"?/)
      link.download = match?.[1] || `${activeStore.name}_bookkeeping.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      toast.success('Records exported')
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    if (!activeStore) return
    // Guard against a race: switching `days` (or stores) quickly fires a
    // new request before the previous one resolves. Without this flag,
    // whichever response arrives LAST wins regardless of which one
    // actually matches the current selection - e.g. click "7 days" then
    // immediately "90 days", and if the smaller 7-day request happens to
    // finish after the 90-day one, the chart would silently show 7 days
    // of data while the dropdown still reads "90 days".
    let cancelled = false
    const fetch = async () => {
      setLoading(true)
      try {
        const { data } = await api.get(`/stores/${activeStore.id}/insights/trend/`, { params: { days } })
        if (!cancelled) setTrend(data.trend)
      } catch (err) {
        if (!cancelled) toast.error(getErrorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetch()
    return () => { cancelled = true }
  }, [activeStore, days])

  const totalRevenue = trend.reduce((s, d) => s + d.revenue, 0)
  const totalProfit = trend.reduce((s, d) => s + d.profit, 0)

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5 gap-2">
        <h1 className="text-xl font-bold text-slate-text">Insights</h1>
        <div className="flex items-center gap-2">
          {activeStore?.role === 'OWNER' && (
            <button onClick={handleExport} disabled={exporting} className="btn-ghost flex items-center gap-2 text-sm" title="Export bookkeeping records (CSV) - useful for loan applications">
              <Download size={16} /><span className="hidden sm:inline">{exporting ? 'Exporting...' : 'Export records'}</span>
            </button>
          )}
          <select
            value={days}
            onChange={e => {
              const value = Number(e.target.value)
              if (value > maxHistoryDays) {
                openUpgradeModal({
                  feature: 'long_term_history',
                  title: 'Unlock Longer History',
                  description: `The Free plan shows the last ${maxHistoryDays} days. Upgrade to Pro to look back further.`,
                })
                return
              }
              setDays(value)
            }}
            className="input w-auto text-sm py-2"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>{maxHistoryDays < 30 ? 'Last 30 days \ud83d\udd12 Pro' : 'Last 30 days'}</option>
            <option value={90}>{maxHistoryDays < 90 ? 'Last 90 days \ud83d\udd12 Pro' : 'Last 90 days'}</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="card-accent p-4 min-w-0">
          <p className="label mb-1">Total revenue</p>
          <p className="stat-number text-lg leading-tight break-words">{formatCurrency(totalRevenue)}</p>
        </div>
        <div className="card p-4 min-w-0">
          <p className="label mb-1">Total net profit</p>
          <p className="stat-number text-lg leading-tight break-words text-brand-500">{formatCurrency(totalProfit)}</p>
        </div>
      </div>

      <div className="card p-4">
        <p className="label mb-4">Revenue & profit trend</p>
        {loading ? (
          <div className="h-48 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : trend.length === 0 ? (
          <div className="h-48 flex items-center justify-center">
            <p className="text-slate-muted text-sm">No data for this period</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trend} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="profit" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={profitColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={profitColor} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="revenue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={revenueColor} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={revenueColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fill: axisColor, fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: axisColor, fontSize: 10 }} tickLine={false} axisLine={false} tickFormatter={v => `₦${(v/1000).toFixed(0)}k`} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="profit" stroke={profitColor} strokeWidth={2} fill="url(#profit)" />
              <Area type="monotone" dataKey="revenue" stroke={revenueColor} strokeWidth={1.5} fill="url(#revenue)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
