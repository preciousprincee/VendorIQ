import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Trash2, ShoppingCart, FileText, Receipt, Undo2, AlertTriangle, WifiOff, CheckCircle2 } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useOffline } from '../context/OfflineContext'
import api, { isNetworkError } from '../lib/api'
import { formatCurrency, formatDateTime, getErrorMessage } from '../lib/utils'
import { methodLabel } from '../lib/offline/money'
import { receiptFromSale } from '../lib/offline/receipt'
import { listLocalSales } from '../lib/offline/sales'
import toast from 'react-hot-toast'
import ConfirmDialog from '../components/ConfirmDialog'
import PosScreen from '../components/pos/PosScreen'
import ReceiptModal from '../components/pos/ReceiptModal'
import ReturnModal from '../components/pos/ReturnModal'

const STATUS_STYLE = {
  PAID: 'bg-green-500/10 text-green-700 dark:text-green-400',
  PARTIAL: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  UNPAID: 'bg-red-500/10 text-red-700 dark:text-red-400',
}
const STATUS_LABEL = { PAID: 'Paid', PARTIAL: 'Part paid', UNPAID: 'On credit' }

function Badge({ className = '', children }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${className}`}>{children}</span>
}

export default function SalesPage() {
  const { activeStore } = useStore()
  const { pending, failed, online } = useOffline()
  const navigate = useNavigate()
  const isCashier = activeStore?.role === 'CASHIER'
  const canManage = !isCashier // owners and managers

  const [sales, setSales] = useState([])
  const [localSales, setLocalSales] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [offlineView, setOfflineView] = useState(false)
  const [view, setView] = useState('list') // list | new
  const [filter, setFilter] = useState('all') // all | review | unpaid
  const fetchSalesRef = useRef(0)

  const [receiptFor, setReceiptFor] = useState(null) // {receipt, status, error, phone}
  const [returnFor, setReturnFor] = useState(null)
  const [creatingInvoiceFor, setCreatingInvoiceFor] = useState(null)
  const [invoiceModalSale, setInvoiceModalSale] = useState(null)
  const [invoiceForm, setInvoiceForm] = useState({ customerName: '', customerEmail: '', customerPhone: '' })
  const [deletingId, setDeletingId] = useState(null)
  const [pendingDeleteSale, setPendingDeleteSale] = useState(null)

  const fetchSales = useCallback(async () => {
    if (!activeStore) return
    // Same request-counter guard as ProductsPage/InvoicesPage - switching
    // stores quickly could let a slower response for the OLD store land
    // after the new store's data has already loaded.
    const requestId = ++fetchSalesRef.current
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/sales/`, { params: filter === 'review' ? { needs_review: 1 } : {} })
      if (requestId !== fetchSalesRef.current) return
      setSales(data.sales || [])
      setSummary(data.summary || null)
      setOfflineView(false)
    } catch (err) {
      if (requestId !== fetchSalesRef.current) return
      if (isNetworkError(err)) setOfflineView(true) // show what's on this device instead of an error
      else toast.error(getErrorMessage(err))
    } finally {
      if (requestId === fetchSalesRef.current) setLoading(false)
    }
  }, [activeStore, filter])

  const loadLocal = useCallback(async () => {
    if (!activeStore) return
    setLocalSales((await listLocalSales(activeStore.id)).filter((s) => s.status === 'pending' || s.status === 'failed'))
  }, [activeStore])

  useEffect(() => { fetchSales() }, [fetchSales])
  // Whenever the outbox changes (a sale queued, or finished syncing) refresh both lists.
  useEffect(() => { loadLocal(); if (pending === 0) fetchSales() }, [pending, failed.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const openInvoiceModal = (sale) => {
    setInvoiceForm({ customerName: sale.customer?.name || '', customerEmail: '', customerPhone: '' })
    setInvoiceModalSale(sale)
  }

  useEffect(() => {
    if (!invoiceModalSale) return undefined
    const onKeyDown = (e) => { if (e.key === 'Escape') setInvoiceModalSale(null) }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [invoiceModalSale])

  const handleCreateInvoice = async (e) => {
    e.preventDefault()
    const sale = invoiceModalSale
    const customerName = invoiceForm.customerName.trim()
    if (!customerName) { toast.error('Customer name is required'); return }
    setCreatingInvoiceFor(sale.id)
    try {
      await api.post(`/stores/${activeStore.id}/sales/${sale.id}/create-invoice/`, {
        customerName,
        customerEmail: invoiceForm.customerEmail || undefined,
        customerPhone: invoiceForm.customerPhone || undefined,
      })
      toast.success('Invoice created')
      setInvoiceModalSale(null)
      navigate('/invoices')
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setCreatingInvoiceFor(null)
    }
  }

  const handleDeleteSale = async () => {
    const sale = pendingDeleteSale
    setDeletingId(sale.id)
    try {
      await api.delete(`/stores/${activeStore.id}/sales/${sale.id}/`)
      toast.success('Sale deleted, stock restored')
      setPendingDeleteSale(null)
      fetchSales()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeletingId(null)
    }
  }

  const markReviewed = async (sale) => {
    try {
      await api.patch(`/stores/${activeStore.id}/sales/${sale.id}/review/`)
      setSales((list) => list.map((s) => (s.id === sale.id ? { ...s, needs_review: false } : s)))
      setSummary((s) => (s ? { ...s, needsReviewCount: Math.max(0, (s.needsReviewCount || 1) - 1) } : s))
    } catch (err) {
      toast.error(getErrorMessage(err))
    }
  }

  if (view === 'new') {
    return <PosScreen onExit={() => { setView('list'); fetchSales(); loadLocal() }} />
  }

  const visibleSales = filter === 'unpaid' ? sales.filter((s) => s.payment_status !== 'PAID') : sales
  const reviewCount = summary?.needsReviewCount || 0

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Sales</h1>
        <button onClick={() => setView('new')} aria-label="Add new sale" className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center hover:bg-brand-600 transition-colors flex-shrink-0">
          <Plus size={18} />
        </button>
      </div>

      {summary && canManage && (
        <div className="grid grid-cols-3 gap-3 mb-5">
          <div className="card p-3 min-w-0">
            <p className="label mb-1">Revenue</p>
            <p className="stat-number text-sm leading-tight break-words">{formatCurrency(summary.totalRevenue)}</p>
          </div>
          <div className="card p-3 min-w-0">
            <p className="label mb-1">Profit</p>
            <p className="stat-number text-sm leading-tight break-words text-brand-500">{formatCurrency(summary.totalProfit)}</p>
          </div>
          <div className="card p-3 min-w-0">
            <p className="label mb-1">Transactions</p>
            <p className="stat-number text-sm leading-tight">{summary.totalTransactions}</p>
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-4 overflow-x-auto">
        {[['all', 'All'], ['unpaid', 'Unpaid'], ...(canManage ? [['review', `Needs review${reviewCount ? ` (${reviewCount})` : ''}`]] : [])].map(([key, label]) => (
          <button key={key} onClick={() => setFilter(key)}
            className={`px-3 py-1.5 rounded-full text-xs border whitespace-nowrap ${filter === key ? 'bg-brand-500 border-brand-500 text-white' : 'border-navy-600 text-slate-muted hover:text-slate-text'}`}>
            {label}
          </button>
        ))}
      </div>

      {offlineView && (
        <p className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300 bg-amber-500/10 rounded-lg px-3 py-2 mb-4">
          <WifiOff size={14} />You're offline - showing sales made on this device. The full history appears when you're back online.
        </p>
      )}

      {localSales.length > 0 && (
        <div className="card divide-y divide-navy-700 mb-4 border border-amber-500/30">
          {localSales.map((s) => (
            <div key={s.clientId} className="px-4 py-3 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-text">{formatDateTime(s.createdAt)}</p>
                <p className="text-xs text-slate-dim break-words">{s.receipt.items.map((i) => `${i.name} ×${i.quantity}`).join(', ')}</p>
                <div className="mt-1">
                  {s.status === 'failed'
                    ? <Badge className="bg-red-500/10 text-red-700 dark:text-red-400"><AlertTriangle size={11} />Not accepted</Badge>
                    : <Badge className="bg-amber-500/10 text-amber-700 dark:text-amber-300"><WifiOff size={11} />Waiting to sync</Badge>}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="font-mono text-sm text-slate-text">{formatCurrency(s.receipt.total)}</p>
                <button onClick={() => setReceiptFor({ receipt: s.receipt, status: s.status, error: s.error })} className="text-xs text-brand-500 hover:underline mt-1">Receipt</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">{[1, 2, 3].map((i) => <div key={i} className="card h-16 animate-pulse" />)}</div>
      ) : visibleSales.length === 0 ? (
        <div className="card p-10 text-center">
          <ShoppingCart size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">
            {filter === 'review' ? 'Nothing needs review.' : filter === 'unpaid' ? 'No unpaid sales.' : offlineView ? 'No sales on this device yet.' : 'No sales yet. Record your first sale.'}
          </p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {visibleSales.map((sale) => {
            const returnable = (sale.sale_items || []).some((i) => i.quantity - (i.returned_quantity || 0) > 0)
            const paymentMethods = [...new Set((sale.payments || []).filter((p) => !p.is_debt_payment).map((p) => methodLabel(p.method)))]
            return (
              <div key={sale.id} className="px-4 py-3 flex gap-3 min-w-0">
                <div className="w-9 h-9 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center text-brand-600 dark:text-brand-400 flex-shrink-0">
                  <ShoppingCart size={15} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2 min-w-0">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-text truncate">{formatDateTime(sale.created_at)} <span className="text-xs text-slate-dim font-mono">#{sale.receipt_no}</span></p>
                      <p className="text-xs text-slate-dim mt-0.5 break-words">
                        {(sale.sale_items ?? []).map((i) => `${i.product?.name || 'Unknown'} ×${i.quantity}`).join(', ')}
                      </p>
                      <p className="text-xs text-slate-dim/70 mt-0.5 truncate">
                        {[sale.recorded_by_name && `Recorded by ${sale.recorded_by_name}`, sale.customer?.name && `for ${sale.customer.name}`].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="font-mono text-sm text-slate-text">{formatCurrency(sale.total_amount)}</p>
                      {canManage && sale.total_profit !== undefined && <p className="font-mono text-xs text-brand-500">{formatCurrency(sale.total_profit)} profit</p>}
                    </div>
                  </div>

                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge className={STATUS_STYLE[sale.payment_status]}>
                      {STATUS_LABEL[sale.payment_status]}{sale.payment_status !== 'PAID' ? ` · owes ${formatCurrency(sale.balance_due)}` : ''}
                    </Badge>
                    {paymentMethods.length > 0 && <Badge className="bg-navy-700 text-slate-muted">{paymentMethods.join(' + ')}</Badge>}
                    {Number(sale.discount_amount) > 0 && <Badge className="bg-navy-700 text-slate-muted">Discount {formatCurrency(sale.discount_amount)}</Badge>}
                    {Number(sale.returned_amount) > 0 && <Badge className="bg-navy-700 text-slate-muted">Returned {formatCurrency(sale.returned_amount)}</Badge>}
                    {sale.synced_at && <Badge className="bg-navy-700 text-slate-muted"><CheckCircle2 size={11} />Synced from offline</Badge>}
                    {canManage && sale.needs_review && <Badge className="bg-amber-500/10 text-amber-700 dark:text-amber-300"><AlertTriangle size={11} />Needs review</Badge>}
                  </div>

                  {canManage && sale.needs_review && (
                    <div className="mt-2 rounded-lg bg-amber-500/10 px-3 py-2">
                      <p className="text-xs text-amber-800 dark:text-amber-200 whitespace-pre-line">{sale.review_notes || 'Flagged for review.'}</p>
                      <button onClick={() => markReviewed(sale)} className="text-xs font-semibold text-amber-800 dark:text-amber-200 underline mt-1">Mark as reviewed</button>
                    </div>
                  )}

                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
                    <button onClick={() => setReceiptFor({ receipt: receiptFromSale(sale, activeStore), status: 'synced', phone: sale.customer?.phone })}
                      className="flex items-center gap-1.5 text-xs text-slate-dim hover:text-brand-500 transition-colors"><Receipt size={13} />Receipt</button>
                    {canManage && returnable && (
                      <button onClick={() => setReturnFor(sale)} className="flex items-center gap-1.5 text-xs text-slate-dim hover:text-brand-500 transition-colors"><Undo2 size={13} />Return</button>
                    )}
                    <button onClick={() => openInvoiceModal(sale)} disabled={creatingInvoiceFor === sale.id}
                      className="flex items-center gap-1.5 text-xs text-slate-dim hover:text-brand-500 transition-colors"><FileText size={13} />Create invoice</button>
                    <button onClick={() => setPendingDeleteSale(sale)} disabled={deletingId === sale.id}
                      className="flex items-center gap-1.5 text-xs text-slate-dim hover:text-red-500 dark:hover:text-red-400 transition-colors">
                      <Trash2 size={13} />{deletingId === sale.id ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {receiptFor && (
        <ReceiptModal receipt={receiptFor.receipt} syncStatus={receiptFor.status} syncError={receiptFor.error}
          customerPhone={receiptFor.phone} onClose={() => setReceiptFor(null)} />
      )}

      {returnFor && (
        <ReturnModal storeId={activeStore.id} sale={returnFor} onClose={() => setReturnFor(null)}
          onDone={() => { setReturnFor(null); fetchSales() }} />
      )}

      {invoiceModalSale && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => setInvoiceModalSale(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="sale-invoice-modal-title" className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <h3 id="sale-invoice-modal-title" className="text-sm font-semibold text-slate-text mb-4">Create invoice for this sale</h3>
            <form onSubmit={handleCreateInvoice} className="space-y-3">
              <div>
                <label htmlFor="sale-inv-customer-name" className="label">Customer name</label>
                <input id="sale-inv-customer-name" className="input" placeholder="e.g. Adaeze Okafor" autoFocus required
                  value={invoiceForm.customerName} onChange={(e) => setInvoiceForm((f) => ({ ...f, customerName: e.target.value }))} />
              </div>
              <div>
                <label htmlFor="sale-inv-email" className="label">Email <span className="text-slate-dim normal-case">(optional)</span></label>
                <input id="sale-inv-email" type="email" className="input" placeholder="customer@example.com"
                  value={invoiceForm.customerEmail} onChange={(e) => setInvoiceForm((f) => ({ ...f, customerEmail: e.target.value }))} />
              </div>
              <div>
                <label htmlFor="sale-inv-phone" className="label">Phone <span className="text-slate-dim normal-case">(optional)</span></label>
                <input id="sale-inv-phone" className="input" placeholder="080..."
                  value={invoiceForm.customerPhone} onChange={(e) => setInvoiceForm((f) => ({ ...f, customerPhone: e.target.value }))} />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setInvoiceModalSale(null)} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={creatingInvoiceFor === invoiceModalSale.id} className="btn-primary flex-1">
                  {creatingInvoiceFor === invoiceModalSale.id ? 'Creating...' : 'Create invoice'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!pendingDeleteSale}
        title="Delete this sale?"
        message="Stock for its items will be restored to inventory. This cannot be undone."
        confirmLabel="Delete sale"
        loading={!!deletingId}
        onConfirm={handleDeleteSale}
        onCancel={() => setPendingDeleteSale(null)}
      />
    </div>
  )
}
