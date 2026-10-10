import { useState, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Clock, X, Printer, WifiOff, CalendarDays } from 'lucide-react'
import toast from 'react-hot-toast'
import { useStore } from '../context/StoreContext'
import { useOffline } from '../context/OfflineContext'
import api from '../lib/api'
import { saveCatalogShift } from '../lib/offline/catalog'
import { parseMoney, toMoney, methodLabel } from '../lib/offline/money'
import { formatCurrency, formatDateTime, getErrorMessage } from '../lib/utils'

const methodRows = (label, byMethod) => Object.entries(byMethod || {})
  .filter(([, v]) => v > 0)
  .map(([m, v]) => [`${label} - ${methodLabel(m)}`, formatCurrency(v)])

/** Report rows for a summary object returned by the API. */
function summaryRows(s) {
  return [
    ['Sales made', String(s.sales_count)],
    ['Gross sales', formatCurrency(s.gross_sales)],
    ['Discounts given', `-${formatCurrency(s.discounts)}`],
    ['Goods returned', `${s.returns_count} (${formatCurrency(s.returns_value)})`],
    ['Put on credit', formatCurrency(s.credit_given)],
    ...methodRows('Received', s.received_by_method),
    ...methodRows('Debt collected', s.debt_collected_by_method),
    ...methodRows('Refunded', s.refunded_by_method),
    ['Total money received', formatCurrency(s.total_received), true],
  ]
}

function ReportModal({ title, subtitle, rows, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return createPortal(
    <div className="receipt-portal fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className="card w-full sm:max-w-sm max-h-[92vh] flex flex-col rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="no-print flex items-center justify-between px-4 pt-3">
          <p className="text-sm font-semibold text-slate-text">{title}</p>
          <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
        </div>
        <div className="receipt-scroll overflow-y-auto p-4">
          <div className="receipt-paper text-slate-text text-[13px] leading-snug">
            <p className="text-center font-bold text-base">{title}</p>
            {subtitle && <p className="text-center text-xs mb-3">{subtitle}</p>}
            <div className="border-t border-dashed border-slate-dim/50 pt-2 space-y-1">
              {rows.map(([label, value, bold], i) => (
                <div key={i} className={`flex justify-between gap-3 ${bold ? 'font-bold border-t border-dashed border-slate-dim/50 pt-1 mt-1' : ''}`}>
                  <span>{label}</span><span className="font-mono text-right">{value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="no-print flex gap-2 p-3 border-t border-navy-700">
          <button onClick={() => window.print()} className="btn-ghost flex-1 flex items-center justify-center gap-1.5 text-xs"><Printer size={14} />Print</button>
          <button onClick={onClose} className="btn-primary flex-1 text-xs">Done</button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function shiftRows(shift, summary) {
  const expected = shift.expected_cash ?? shift.live_expected_cash
  const rows = [
    ['Cashier', shift.opened_by_name],
    ['Opened', formatDateTime(shift.opened_at)],
    ['Closed', shift.closed_at ? formatDateTime(shift.closed_at) : 'still open'],
    ['Opening cash', formatCurrency(shift.opening_float)],
    ['Cash taken in', formatCurrency(summary.cash_in)],
    ['Cash given out (refunds)', `-${formatCurrency(summary.cash_out)}`],
    ['Cash expected in till', formatCurrency(expected), true],
  ]
  if (shift.counted_cash != null) {
    rows.push(['Cash counted', formatCurrency(shift.counted_cash)])
    const v = Number(shift.variance)
    rows.push(['Difference', v === 0 ? 'Balanced' : `${v > 0 ? 'Over' : 'Short'} ${formatCurrency(Math.abs(v))}`, true])
  }
  return [...rows, ['', ''], ...summaryRows(summary)]
}

export default function ShiftsPage() {
  const { activeStore } = useStore()
  const { online, reloadCatalog } = useOffline()
  const canManage = activeStore?.role !== 'CASHIER'
  const base = `/stores/${activeStore?.id}`

  const [current, setCurrent] = useState(undefined) // undefined = loading, null = none
  const [shifts, setShifts] = useState([])
  const [loadError, setLoadError] = useState('')
  const [openingFloat, setOpeningFloat] = useState('')
  const [counted, setCounted] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState(null) // {title, subtitle, rows}
  const [day, setDay] = useState(() => new Date().toLocaleDateString('en-CA')) // YYYY-MM-DD, local

  const load = useCallback(async () => {
    if (!activeStore) return
    try {
      const [cur, list] = await Promise.all([api.get(`${base}/shifts/current/`), api.get(`${base}/shifts/`)])
      setCurrent(cur.data.shift ? cur.data : null)
      setShifts(list.data.shifts)
      setLoadError('')
      await saveCatalogShift(activeStore.id, cur.data.shift || null)
    } catch (err) {
      setLoadError(getErrorMessage(err))
      setCurrent((c) => (c === undefined ? null : c))
    }
  }, [activeStore, base])

  useEffect(() => { load() }, [load])

  const openShift = async (e) => {
    e.preventDefault()
    const value = parseMoney(openingFloat)
    if (Number.isNaN(value)) { toast.error('Enter a valid amount'); return }
    setBusy(true)
    try {
      await api.post(`${base}/shifts/open/`, { openingFloat: toMoney(value) })
      toast.success('Till opened')
      setOpeningFloat('')
      await load()
      reloadCatalog()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally { setBusy(false) }
  }

  const closeShift = async (e) => {
    e.preventDefault()
    const value = parseMoney(counted)
    if (counted.trim() === '' || Number.isNaN(value)) { toast.error('Enter the cash you counted'); return }
    setBusy(true)
    try {
      const { data } = await api.post(`${base}/shifts/${current.shift.id}/close/`, { countedCash: toMoney(value), notes })
      toast.success('Till closed')
      setCounted(''); setNotes('')
      setReport({ title: 'Shift report', subtitle: activeStore.name, rows: shiftRows(data.shift, data.summary) })
      await load()
      reloadCatalog()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally { setBusy(false) }
  }

  const viewShift = async (shift) => {
    try {
      const { data } = await api.get(`${base}/shifts/${shift.id}/`)
      setReport({ title: 'Shift report', subtitle: activeStore.name, rows: shiftRows(data.shift, data.summary) })
    } catch (err) { toast.error(getErrorMessage(err)) }
  }

  const viewDay = async () => {
    try {
      const { data } = await api.get(`${base}/reports/daily/`, { params: { date: day } })
      const s = data.summary
      setReport({
        title: 'Daily summary',
        subtitle: `${activeStore.name} - ${new Date(`${data.date}T12:00:00`).toLocaleDateString('en-NG', { dateStyle: 'long' })}`,
        rows: [
          ['Net sales', formatCurrency(data.netSales), true],
          ['Net profit', formatCurrency(data.netProfit)],
          ['Expenses recorded', formatCurrency(data.expenses)],
          ['', ''],
          ...summaryRows(s),
          ['', ''],
          ['Cash taken in', formatCurrency(s.cash_in)],
          ['Cash given out', `-${formatCurrency(s.cash_out)}`],
          ['Net cash movement', formatCurrency(s.net_cash_movement), true],
        ],
      })
    } catch (err) { toast.error(getErrorMessage(err)) }
  }

  const live = current?.shift

  return (
    <div className="p-5 lg:p-6 max-w-2xl animate-fade-in">
      <h1 className="text-xl font-bold text-slate-text mb-1">Till & shifts</h1>
      <p className="text-xs text-slate-dim mb-5">Count the cash in when you start and out when you finish, and see whether it matches what the system expects.</p>

      {!online && (
        <p className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-500/10 rounded-lg px-3 py-2 mb-4">
          <WifiOff size={14} />Opening and closing the till needs an internet connection. You can keep selling while offline.
        </p>
      )}
      {loadError && online && <p role="alert" className="text-xs text-red-500 mb-4">{loadError}</p>}

      {current === undefined ? <div className="card h-32 animate-pulse mb-5" /> : live ? (
        <div className="card p-4 mb-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            <p className="text-sm font-semibold text-slate-text">Till open since {formatDateTime(live.opened_at)}</p>
          </div>
          <div className="grid grid-cols-2 gap-3 mb-4 text-sm">
            <div className="rounded-xl bg-navy-700/40 p-3"><p className="label mb-0.5">Opening cash</p><p className="font-mono">{formatCurrency(live.opening_float)}</p></div>
            <div className="rounded-xl bg-navy-700/40 p-3"><p className="label mb-0.5">Cash expected now</p><p className="font-mono">{formatCurrency(live.live_expected_cash)}</p></div>
          </div>
          <form onSubmit={closeShift} className="space-y-3">
            <div>
              <label htmlFor="shift-counted" className="label">Cash counted in the till</label>
              <input id="shift-counted" className="input font-mono" inputMode="decimal" placeholder="0" value={counted}
                onChange={(e) => setCounted(e.target.value.replace(/[^0-9.,]/g, ''))} />
            </div>
            <div>
              <label htmlFor="shift-notes" className="label">Notes <span className="text-slate-dim normal-case">(optional)</span></label>
              <input id="shift-notes" className="input" maxLength={300} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <button type="submit" disabled={busy || !online} className="btn-primary w-full">{busy ? 'Closing...' : 'Close till'}</button>
          </form>
        </div>
      ) : (
        <form onSubmit={openShift} className="card p-4 mb-5 space-y-3">
          <div className="flex items-center gap-2"><Clock size={15} className="text-slate-dim" /><p className="text-sm font-semibold text-slate-text">Open your till</p></div>
          <div>
            <label htmlFor="shift-float" className="label">Cash in the till to start with</label>
            <input id="shift-float" className="input font-mono" inputMode="decimal" placeholder="0" value={openingFloat}
              onChange={(e) => setOpeningFloat(e.target.value.replace(/[^0-9.,]/g, ''))} />
          </div>
          <button type="submit" disabled={busy || !online} className="btn-primary w-full">{busy ? 'Opening...' : 'Open till'}</button>
        </form>
      )}

      {canManage && (
        <div className="card p-4 mb-5">
          <div className="flex items-center gap-2 mb-3"><CalendarDays size={15} className="text-slate-dim" /><p className="text-sm font-semibold text-slate-text">End-of-day summary</p></div>
          <div className="flex gap-2">
            <input type="date" className="input flex-1" aria-label="Day" value={day} max={new Date().toLocaleDateString('en-CA')} onChange={(e) => setDay(e.target.value)} />
            <button onClick={viewDay} disabled={!online || !day} className="btn-primary">View</button>
          </div>
        </div>
      )}

      <p className="label mb-2">{canManage ? 'Recent shifts' : 'Your recent shifts'}</p>
      {shifts.length === 0 ? (
        <div className="card p-6 text-center text-sm text-slate-muted">No shifts yet.</div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {shifts.map((s) => {
            const v = s.variance == null ? null : Number(s.variance)
            return (
              <button key={s.id} onClick={() => viewShift(s)} className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-navy-700/50 transition-colors">
                <div className="min-w-0">
                  <p className="text-sm text-slate-text truncate">{canManage ? `${s.opened_by_name} · ` : ''}{formatDateTime(s.opened_at)}</p>
                  <p className="text-xs text-slate-dim">{s.closed_at ? `Closed ${formatDateTime(s.closed_at)}` : 'Still open'}</p>
                </div>
                {v == null ? <span className="text-xs text-green-600 dark:text-green-400 flex-shrink-0">open</span>
                  : <span className={`text-xs font-mono flex-shrink-0 ${v === 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
                    {v === 0 ? 'Balanced' : `${v > 0 ? 'Over' : 'Short'} ${formatCurrency(Math.abs(v))}`}
                  </span>}
              </button>
            )
          })}
        </div>
      )}

      {report && <ReportModal title={report.title} subtitle={report.subtitle} rows={report.rows} onClose={() => setReport(null)} />}
    </div>
  )
}
