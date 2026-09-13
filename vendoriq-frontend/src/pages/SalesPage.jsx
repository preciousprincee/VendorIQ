import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, ChevronLeft, Trash2, ShoppingCart, Search, ScanLine, FileText } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import api from '../lib/api'
import { formatCurrency, formatDateTime, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'
import ConfirmDialog from '../components/ConfirmDialog'

export default function SalesPage() {
  const { activeStore } = useStore()
  const navigate = useNavigate()
  const [sales, setSales] = useState([])
  const [summary, setSummary] = useState(null)
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [view, setView] = useState('list') // list | new
  const [cart, setCart] = useState([])
  const [search, setSearch] = useState('')
  const fetchSalesRef = useRef(0)
  const [scanning, setScanning] = useState(false)
  const [creatingInvoiceFor, setCreatingInvoiceFor] = useState(null)
  const [invoiceModalSale, setInvoiceModalSale] = useState(null)
  const [invoiceForm, setInvoiceForm] = useState({ customerName: '', customerEmail: '', customerPhone: '' })
  const [deletingId, setDeletingId] = useState(null)
  const [pendingDeleteSale, setPendingDeleteSale] = useState(null)
  const videoRef = useRef(null)
  const scannerRef = useRef(null)

  // Camera cleanup on unmount - stopScan() (the explicit "stop" button)
  // already releases the camera, but nothing released it if the user
  // navigates away mid-scan instead (tapping a nav tab, browser back,
  // switching stores) without tapping stop first. Without this, the
  // camera stream keeps running in the background indefinitely - the
  // camera indicator light stays on and video decoding keeps burning
  // battery/CPU, which matters a lot on the mobile POS use case this page
  // is actually built for, where a cashier moving between screens
  // mid-shift without remembering to stop scanning first is the normal
  // case, not an edge case.
  useEffect(() => {
    return () => { scannerRef.current?.reset() }
  }, [])

  const fetchSales = async () => {
    // Same request-counter guard as ProductsPage/InvoicesPage - switching
    // stores quickly could let a slower response for the OLD store land
    // after the new store's data has already loaded.
    const requestId = ++fetchSalesRef.current
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/sales/`)
      if (requestId !== fetchSalesRef.current) return
      setSales(data.sales || [])
      setSummary(data.summary || null)
    } catch (err) {
      if (requestId === fetchSalesRef.current) toast.error(getErrorMessage(err))
    } finally {
      if (requestId === fetchSalesRef.current) setLoading(false)
    }
  }

  const fetchProducts = async () => {
    const { data } = await api.get(`/stores/${activeStore.id}/products/`)
    setProducts(data.products)
  }

  useEffect(() => { if (activeStore) fetchSales() }, [activeStore])

  const openNew = async () => {
    await fetchProducts()
    setCart([])
    setView('new')
  }

  const addToCart = (product) => {
    setCart(c => {
      const existing = c.find(i => i.productId === product.id)
      if (existing) return c.map(i => i.productId === product.id ? { ...i, quantity: i.quantity + 1 } : i)
     return [...c, { productId: product.id, name: product.name, sellingPrice: product.selling_price, quantity: 1, available: product.quantity }]
    })
  }

  const startScan = async () => {
    try {
      const { BrowserMultiFormatReader } = await import('@zxing/browser')
      const reader = new BrowserMultiFormatReader()
      scannerRef.current = reader
      setScanning(true)
      await reader.decodeFromVideoDevice(undefined, videoRef.current, (result) => {
        if (result) handleScanResult(result.getText())
      })
    } catch {
      toast.error('Camera not available')
      setScanning(false)
    }
  }

  const stopScan = () => {
    scannerRef.current?.reset()
    setScanning(false)
  }

  const handleScanResult = (barcode) => {
    const product = products.find(p => p.barcode === barcode)
    if (!product) {
      toast.error('No product matches that barcode')
      return
    }
    if (product.quantity <= 0) {
      toast.error(`${product.name} is out of stock`)
      return
    }
    addToCart(product)
    toast.success(`${product.name} added`)
    stopScan()
  }

  const openInvoiceModal = (sale) => {
    setInvoiceForm({ customerName: '', customerEmail: '', customerPhone: '' })
    setInvoiceModalSale(sale)
  }

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

  const updateQty = (productId, qty) => {
    const item = cart.find(i => i.productId === productId)
    if (qty > item.available) { toast.error(`Only ${item.available} available`); return }
    if (qty <= 0) { setCart(c => c.filter(i => i.productId !== productId)); return }
    setCart(c => c.map(i => i.productId === productId ? { ...i, quantity: qty } : i))
  }

  const cartTotal = cart.reduce((sum, i) => sum + Number(i.sellingPrice) * i.quantity, 0)

  const handleRecordSale = async () => {
    if (cart.length === 0) return
    setSaving(true)
    try {
      await api.post(`/stores/${activeStore.id}/sales/`, {
        items: cart.map(i => ({ productId: i.productId, quantity: i.quantity }))
      })
      toast.success('Sale recorded')
      setView('list')
      fetchSales()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const filteredProducts = products.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) && p.quantity > 0
  )

  if (view === 'new') return (
    <div className="p-5 max-w-xl animate-fade-in">
      <div className="flex items-center gap-3 mb-5">
        <button onClick={() => { stopScan(); setView('list') }} className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">Record Sale</h1>
      </div>

      <div className="flex gap-2 mb-3">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-dim" />
          <input className="input pl-9" placeholder="Search products to add..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <button type="button" onClick={scanning ? stopScan : startScan}
          className={`flex-shrink-0 px-3 rounded-xl border transition-colors ${scanning ? 'border-brand-500 text-brand-500' : 'border-navy-600 text-slate-muted hover:text-slate-text hover:border-navy-500'}`}>
          <ScanLine size={18} />
        </button>
      </div>

      {scanning && (
        <div className="mb-3 relative rounded-xl overflow-hidden bg-black aspect-video">
          <video ref={videoRef} className="w-full h-full object-cover" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-48 h-24 border-2 border-brand-500 rounded opacity-70" />
          </div>
          <p className="absolute bottom-2 left-0 right-0 text-center text-xs text-white/80">Point the camera at the product's barcode</p>
        </div>
      )}

      <div className="card divide-y divide-navy-700 mb-4 max-h-56 overflow-y-auto">
        {filteredProducts.length === 0 ? (
          <p className="p-4 text-sm text-slate-muted text-center">No products found</p>
        ) : filteredProducts.map(p => (
          <button key={p.id} onClick={() => addToCart(p)}
            className="w-full px-4 py-3 text-left hover:bg-navy-700/50 transition-colors flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-text">{p.name}</p>
              <p className="text-xs text-slate-dim font-mono">{formatCurrency(p.selling_price)} · {p.quantity} in stock</p>
            </div>
            <div className="w-7 h-7 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center text-brand-500 flex-shrink-0">
              <Plus size={14} />
            </div>
          </button>
        ))}
      </div>

      {cart.length > 0 && (
        <>
          <p className="label mb-2">Cart</p>
          <div className="card divide-y divide-navy-700 mb-4">
            {cart.map(item => (
              <div key={item.productId} className="px-4 py-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-text truncate">{item.name}</p>
                  <p className="text-xs text-brand-500 font-mono">{formatCurrency(item.sellingPrice)} each</p>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => updateQty(item.productId, item.quantity - 1)} className="w-7 h-7 rounded-full bg-navy-700 text-slate-text flex items-center justify-center hover:bg-navy-600">−</button>
                  <span className="font-mono text-sm w-6 text-center">{item.quantity}</span>
                  <button onClick={() => updateQty(item.productId, item.quantity + 1)} className="w-7 h-7 rounded-full bg-navy-700 text-slate-text flex items-center justify-center hover:bg-navy-600">+</button>
                  <button onClick={() => setCart(c => c.filter(i => i.productId !== item.productId))} className="text-slate-dim hover:text-red-500 dark:hover:text-red-400 ml-1">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
            <div className="px-4 py-3 flex justify-between">
              <span className="text-sm font-semibold text-slate-text">Total</span>
              <span className="font-mono font-semibold text-brand-500">{formatCurrency(cartTotal)}</span>
            </div>
          </div>

          <button onClick={handleRecordSale} disabled={saving} className="btn-primary w-full">
            {saving ? 'Recording...' : `Record sale · ${formatCurrency(cartTotal)}`}
          </button>
        </>
      )}
    </div>
  )

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Sales</h1>
        <button onClick={openNew} className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center hover:bg-brand-600 transition-colors flex-shrink-0">
          <Plus size={18} />
        </button>
      </div>

      {summary && activeStore?.role !== 'CASHIER' && (
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

      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="card h-16 animate-pulse" />)}</div>
      ) : sales.length === 0 ? (
        <div className="card p-10 text-center">
          <ShoppingCart size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">No sales yet. Record your first sale.</p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {(sales || []).map(sale => (
            <div key={sale.id} className="px-4 py-3 flex gap-3 min-w-0">
              <div className="w-9 h-9 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center text-brand-600 dark:text-brand-400 flex-shrink-0">
                <ShoppingCart size={15} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2 min-w-0">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-text truncate">{formatDateTime(sale.created_at)}</p>
                    <p className="text-xs text-slate-dim mt-0.5 break-words">
                        {(sale.sale_items ?? [])
                        .map(i => `${i.product?.name || 'Unknown'} ×${i.quantity}`)
                        .join(', ')}
                    </p>
                    {sale.recorded_by_name && (
                      <p className="text-xs text-slate-dim/70 mt-0.5 truncate">Recorded by {sale.recorded_by_name}</p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="font-mono text-sm text-slate-text">{formatCurrency(sale.total_amount)}</p>
                    {activeStore?.role !== 'CASHIER' && (
                      <p className="font-mono text-xs text-brand-500">{formatCurrency(sale.total_profit)} profit</p>
                    )}
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-4">
                  <button
                    onClick={() => openInvoiceModal(sale)}
                    disabled={creatingInvoiceFor === sale.id}
                    className="flex items-center gap-1.5 text-xs text-slate-dim hover:text-brand-500 transition-colors"
                  >
                    <FileText size={13} />
                    Create invoice
                  </button>
                  <button
                    onClick={() => setPendingDeleteSale(sale)}
                    disabled={deletingId === sale.id}
                    className="flex items-center gap-1.5 text-xs text-slate-dim hover:text-red-500 dark:hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={13} />
                    {deletingId === sale.id ? 'Deleting...' : 'Delete'}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {invoiceModalSale && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => setInvoiceModalSale(null)}>
          <div className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-slate-text mb-4">Create invoice for this sale</h3>
            <form onSubmit={handleCreateInvoice} className="space-y-3">
              <div>
                <label className="label">Customer name</label>
                <input className="input" placeholder="e.g. Adaeze Okafor" autoFocus required
                  value={invoiceForm.customerName}
                  onChange={e => setInvoiceForm(f => ({ ...f, customerName: e.target.value }))} />
              </div>
              <div>
                <label className="label">Email <span className="text-slate-dim normal-case">(optional)</span></label>
                <input type="email" className="input" placeholder="customer@example.com"
                  value={invoiceForm.customerEmail}
                  onChange={e => setInvoiceForm(f => ({ ...f, customerEmail: e.target.value }))} />
              </div>
              <div>
                <label className="label">Phone <span className="text-slate-dim normal-case">(optional)</span></label>
                <input className="input" placeholder="080..."
                  value={invoiceForm.customerPhone}
                  onChange={e => setInvoiceForm(f => ({ ...f, customerPhone: e.target.value }))} />
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
