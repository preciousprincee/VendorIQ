import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus, Search, ScanLine, Edit2, Trash2, Package, RefreshCw, Eye, EyeOff, ChevronLeft, Clock, X } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useSubscription } from '../context/SubscriptionContext'
import UsageLimit from '../components/billing/UsageLimit'
import ConfirmDialog from '../components/ConfirmDialog'
import BarcodeScanner from '../components/scanner/BarcodeScanner'
import api from '../lib/api'
import { formatCurrency, getErrorMessage, formatDateTime } from '../lib/utils'
import { prepareProductPhoto } from '../lib/image'
import toast from 'react-hot-toast'
import { track } from '../lib/analytics'

const EMPTY_FORM = { name: '', barcode: '', cost_price: '', selling_price: '', quantity: '', low_stock_threshold: '5', category: '', supplier: '', photo: null, photoPreview: null }

const CATEGORY_SUGGESTIONS = ['Cooking Oil', 'Grains & Rice', 'Dairy', 'Beverages', 'Snacks', 'Household', 'Personal Care', 'Frozen Foods', 'Bakery', 'Other']

function ProductAvatar({ name, photoUrl, size = 'md' }) {
  const dims = size === 'lg' ? 'w-20 h-20 text-2xl' : 'w-11 h-11 text-sm'
  const initial = name?.[0]?.toUpperCase() || '?'
  if (photoUrl) {
    return <img src={photoUrl} alt={name} className={`${dims} rounded-xl object-cover flex-shrink-0`} />
  }
  return (
    <div className={`${dims} rounded-xl bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0 font-bold text-brand-600 dark:text-brand-400`}>
      {initial}
    </div>
  )
}

// lockPricing: a cashier editing an existing product. The API neither sends
// them the cost price nor lets them change prices, so the form hides cost,
// disables selling price and leaves both out of the PATCH.
function ProductForm({ initial = EMPTY_FORM, onSave, onCancel, loading, lockPricing = false }) {
  const [form, setForm] = useState(initial)
  const [scanning, setScanning] = useState(false)
  const photoInputRef = useRef(null)
  const [preparingPhoto, setPreparingPhoto] = useState(false)

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const handlePhotoChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setPreparingPhoto(true)
    try {
      // One small photo per product: shrink big phone pictures here, before upload.
      const small = await prepareProductPhoto(file)
      setForm(f => ({ ...f, photo: small, photoPreview: URL.createObjectURL(small), removePhoto: false }))
    } catch (err) {
      toast.error(err.message)
      if (photoInputRef.current) photoInputRef.current.value = ''
    } finally {
      setPreparingPhoto(false)
    }
  }

  const removePhoto = () => {
    setForm(f => ({ ...f, photo: null, photoPreview: null, removePhoto: true }))
    if (photoInputRef.current) photoInputRef.current.value = ''
  }

  const handleScanned = (text) => {
    setForm(f => ({ ...f, barcode: text }))
    setScanning(false)
    toast.success('Barcode scanned')
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave({
      name: form.name,
      barcode: form.barcode || undefined,
      ...(lockPricing ? {} : { cost_price: Number(form.cost_price), selling_price: Number(form.selling_price) }),
      quantity: Number(form.quantity),
      low_stock_threshold: Number(form.low_stock_threshold),
      category: form.category || undefined,
      supplier: form.supplier || undefined,
      photo: form.photo || undefined,
      removePhoto: form.removePhoto || false,
    })
  }

  const margin = form.cost_price && form.selling_price
    ? (((Number(form.selling_price) - Number(form.cost_price)) / Number(form.selling_price)) * 100).toFixed(1)
    : null

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label">Product photo <span className="text-slate-dim normal-case">(optional)</span></label>
        <div className="flex items-center gap-4">
          <ProductAvatar name={form.name} photoUrl={form.photoPreview || (!form.removePhoto ? form.existingPhotoUrl : null)} size="lg" />
          <div className="flex-1 min-w-0 flex flex-col gap-2">
            <input ref={photoInputRef} type="file" accept="image/*" onChange={handlePhotoChange} className="hidden" id="product-photo-input" />
            <div className="flex gap-2">
              <label htmlFor="product-photo-input" className="btn-ghost text-xs py-1.5 px-3 cursor-pointer inline-flex items-center">
                {preparingPhoto ? 'Preparing photo...' : 'Upload photo'}
              </label>
              {(form.photoPreview || (!form.removePhoto && form.existingPhotoUrl)) && (
                <button type="button" onClick={removePhoto} className="text-xs text-red-500 dark:text-red-400 hover:underline">
                  Remove
                </button>
              )}
            </div>
            <p className="text-xs text-slate-dim">One photo per product, resized automatically. Without one, products show an initial instead.</p>
          </div>
        </div>
      </div>

      <div>
        <label htmlFor="prod-name" className="label">Product name</label>
        <input id="prod-name" className="input" placeholder="e.g. Indomie Noodles (70g)" value={form.name} onChange={set('name')} required />
      </div>

      <div>
        <label htmlFor="prod-barcode" className="label">Barcode <span className="text-slate-dim normal-case">(optional)</span></label>
        <div className="flex gap-2">
          <input id="prod-barcode" className="input" placeholder="Scan or enter manually" value={form.barcode} onChange={set('barcode')} />
          <button type="button" onClick={() => setScanning(v => !v)} aria-label={scanning ? 'Stop barcode scan' : 'Scan barcode'}
            className={`flex-shrink-0 px-3 rounded-xl border transition-colors ${scanning ? 'border-brand-500 text-brand-500' : 'border-navy-600 text-slate-muted hover:text-slate-text hover:border-navy-500'}`}>
            <ScanLine size={18} />
          </button>
        </div>
        {scanning && (
          <BarcodeScanner
            className="mt-2"
            onDetected={handleScanned}
            onError={() => { /* the message is shown inside the scanner */ }}
          />
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        {!lockPricing && (
          <div>
            <label htmlFor="prod-cost" className="label">Cost price (₦)</label>
            <input id="prod-cost" type="number" className="input font-mono" placeholder="0" min="0" step="0.01"
              value={form.cost_price} onChange={set('cost_price')} required />
          </div>
        )}
        <div>
          <label htmlFor="prod-price" className="label">Selling price (₦)</label>
          <input id="prod-price" type="number" className="input font-mono" placeholder="0" min="0" step="0.01"
            value={form.selling_price} onChange={set('selling_price')} required disabled={lockPricing} />
        </div>
      </div>

      {margin !== null && (
        <p className="text-xs text-slate-muted">
          Margin: <span className={`font-mono font-medium ${Number(margin) > 0 ? 'text-brand-500' : 'text-red-500 dark:text-red-400'}`}>{margin}%</span>
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="prod-qty" className="label">Quantity in stock</label>
          <input id="prod-qty" type="number" className="input font-mono" placeholder="0" min="0"
            value={form.quantity} onChange={set('quantity')} required />
        </div>
        <div>
          <label htmlFor="prod-low-stock" className="label">Low stock alert at</label>
          <input id="prod-low-stock" type="number" className="input font-mono" placeholder="5" min="0"
            value={form.low_stock_threshold} onChange={set('low_stock_threshold')} />
        </div>
      </div>
      <p className="text-xs text-slate-dim -mt-2">You'll be alerted when stock falls below this.</p>

      <div>
        <label htmlFor="prod-category" className="label">Category <span className="text-slate-dim normal-case">(optional)</span></label>
        <input id="prod-category" className="input" list="category-suggestions" placeholder="e.g. Cooking Oil" value={form.category} onChange={set('category')} />
        <datalist id="category-suggestions">
          {CATEGORY_SUGGESTIONS.map(c => <option key={c} value={c} />)}
        </datalist>
      </div>

      <div>
        <label htmlFor="prod-supplier" className="label">Supplier <span className="text-slate-dim normal-case">(optional)</span></label>
        <input id="prod-supplier" className="input" placeholder="e.g. PZ Cussons" value={form.supplier} onChange={set('supplier')} />
      </div>

      <div className="flex gap-3 pt-2">
        <button type="button" onClick={onCancel} className="btn-ghost flex-1">Cancel</button>
        <button type="submit" disabled={loading} className="btn-primary flex-1">
          {loading ? 'Saving...' : 'Save Changes'}
        </button>
      </div>
    </form>
  )
}

export default function ProductsPage() {
  const { activeStore } = useStore()
  const { limits } = useSubscription()
  const [products, setProducts] = useState([])
  const [summary, setSummary] = useState(null)
  const [truncated, setTruncated] = useState(false)
  const fetchRequestRef = useRef(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  // Deletion requests. A cashier can't delete products; they ask (with a remark) and
  // the owner / managers approve or decline. Owners and managers see every pending
  // request; a cashier sees their own.
  const isCashier = activeStore?.role === 'CASHIER'
  const [searchParams, setSearchParams] = useSearchParams()
  const [requests, setRequests] = useState([])
  const [requestsLoaded, setRequestsLoaded] = useState(false)
  const [requestFor, setRequestFor] = useState(null)       // product a cashier is asking to delete
  const [remark, setRemark] = useState('')
  const [sendingRequest, setSendingRequest] = useState(false)
  const [showRequests, setShowRequests] = useState(false)
  const [decisionNotes, setDecisionNotes] = useState({})
  const [deciding, setDeciding] = useState(null)           // request id being processed
  const [confirmApprove, setConfirmApprove] = useState(null)
  const pendingByProduct = new Map(requests.map((r) => [r.product_id, r]))
  const [search, setSearch] = useState('')
  const [view, setView] = useState('list') // list | add | edit | restock
  const [selected, setSelected] = useState(null)
  const [restockQty, setRestockQty] = useState('')
  const [scanningSearch, setScanningSearch] = useState(false)
  const [hideValues, setHideValues] = useState(() => localStorage.getItem('viq_hide_stock_value') === 'true')

  const toggleHideValues = () => {
    setHideValues(v => {
      localStorage.setItem('viq_hide_stock_value', String(!v))
      return !v
    })
  }

  const fetchProducts = async () => {
    // Request-counter guard: fetchProducts is called both from the effect
    // below (on every keystroke in search) AND directly after mutations
    // (add/delete/restock). Typing quickly fires overlapping requests -
    // without this, a slower response for an OLDER search term could
    // resolve after a newer one and silently overwrite it, showing stale
    // results for whatever you typed a moment ago instead of what's
    // currently in the search box. Using a ref (not a per-effect closure
    // flag) means this protects every call site, not just the effect.
    const requestId = ++fetchRequestRef.current
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/products/`, { params: { search } })
      if (requestId !== fetchRequestRef.current) return
      setProducts(data.products)
      setSummary(data.summary)
      setTruncated(!!data.truncated)
    } catch (err) {
      if (requestId === fetchRequestRef.current) toast.error(getErrorMessage(err))
    } finally {
      if (requestId === fetchRequestRef.current) setLoading(false)
    }
  }

  useEffect(() => { if (activeStore) fetchProducts() }, [activeStore, search])

  // The camera itself lives in <BarcodeScanner>, which starts when it mounts
  // and releases the camera when it unmounts (navigating away included).
  const handleSearchScanned = (text) => {
    setSearch(text)
    setScanningSearch(false)
  }

  const toRequestPayload = (formData) => {
    const { photo, removePhoto, ...rest } = formData
    if (!photo && !removePhoto) return rest
    const body = new FormData()
    Object.entries(rest).forEach(([k, v]) => {
      if (v !== undefined && v !== null) body.append(k, v)
    })
    if (photo) body.append('photo', photo)
    else if (removePhoto) body.append('photo', '')
    return body
  }

  const handleAdd = async (formData) => {
    setSaving(true)
    try {
      await api.post(`/stores/${activeStore.id}/products/`, toRequestPayload(formData))
      track('product_created', { has_photo: !!formData.photo })
      toast.success('Product added')
      setView('list')
      fetchProducts()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = async (formData) => {
    setSaving(true)
    try {
      await api.patch(`/stores/${activeStore.id}/products/${selected.id}/`, toRequestPayload(formData))
      toast.success('Product updated')
      setView('list')
      setSelected(null)
      fetchProducts()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = (product) => {
    if (isCashier) {
      if (pendingByProduct.has(product.id)) { toast('This product is already waiting for approval.'); return }
      setRemark('')
      setRequestFor(product)
      return
    }
    setPendingDelete(product)
  }

  const fetchRequests = async () => {
    if (!activeStore) return
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/deletion-requests/`)
      setRequests(data.requests)
    } catch { /* non-critical: the product list still works */ } finally {
      setRequestsLoaded(true)
    }
  }

  useEffect(() => { fetchRequests() }, [activeStore]) // eslint-disable-line react-hooks/exhaustive-deps

  // The bell links here (/products?requests=1): open the review panel once the requests have loaded.
  useEffect(() => {
    if (!requestsLoaded || searchParams.get('requests') !== '1') return
    if (!isCashier && requests.length > 0) setShowRequests(true)
    const next = new URLSearchParams(searchParams)
    next.delete('requests')
    setSearchParams(next, { replace: true })
  }, [requestsLoaded, requests, searchParams]) // eslint-disable-line react-hooks/exhaustive-deps

  const submitRequest = async (e) => {
    e.preventDefault()
    const text = remark.trim()
    if (text.length < 5) { toast.error('Please explain why (at least 5 characters)'); return }
    setSendingRequest(true)
    try {
      await api.post(`/stores/${activeStore.id}/products/${requestFor.id}/deletion-request/`, { remark: text })
      track('deletion_request_created')
      toast.success('Request sent - your manager and the owner have been notified')
      setRequestFor(null)
      setRemark('')
      fetchRequests()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSendingRequest(false)
    }
  }

  const decide = async (req, action) => {
    setDeciding(req.id)
    try {
      await api.post(`/stores/${activeStore.id}/deletion-requests/${req.id}/${action}/`, { note: (decisionNotes[req.id] || '').trim() })
      track('deletion_request_decided', { decision: action })
      toast.success(action === 'approve' ? 'Approved - product deleted' : action === 'reject' ? 'Request declined' : 'Request cancelled')
      await fetchRequests()
      if (action === 'approve') fetchProducts()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeciding(null)
      setConfirmApprove(null)
    }
  }

  const confirmDelete = async () => {
    const product = pendingDelete
    setDeleting(true)
    try {
      await api.delete(`/stores/${activeStore.id}/products/${product.id}/`)
      toast.success('Product deleted')
      fetchProducts()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  const handleRestock = async () => {
    if (!restockQty || Number(restockQty) <= 0) return
    setSaving(true)
    try {
      await api.patch(`/stores/${activeStore.id}/products/${selected.id}/restock/`, { quantity: Number(restockQty) })
      toast.success(`Added ${restockQty} units`)
      setView('list')
      setSelected(null)
      setRestockQty('')
      fetchProducts()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  if (view === 'add') return (
    <div className="p-5 max-w-lg">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => setView('list')} className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">Add Product</h1>
      </div>
      <ProductForm onSave={handleAdd} onCancel={() => setView('list')} loading={saving} />
    </div>
  )

  if (view === 'edit' && selected) return (
    <div className="p-5 max-w-lg">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => { setView('list'); setSelected(null) }} className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">Edit Product</h1>
      </div>
      <ProductForm
        initial={{
          name: selected.name, barcode: selected.barcode || '', cost_price: selected.cost_price,
          selling_price: selected.selling_price, quantity: selected.quantity,
          low_stock_threshold: selected.low_stock_threshold, category: selected.category || '', supplier: selected.supplier || '',
          photo: null, photoPreview: null, existingPhotoUrl: selected.photo || null, removePhoto: false,
        }}
        onSave={handleEdit} onCancel={() => { setView('list'); setSelected(null) }} loading={saving}
        lockPricing={activeStore?.role === 'CASHIER'}
      />
    </div>
  )

  if (view === 'restock' && selected) return (
    <div className="p-5 max-w-sm">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => { setView('list'); setSelected(null) }} className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">Restock</h1>
      </div>
      <div className="card p-5">
        <p className="text-sm font-semibold text-slate-text mb-1">{selected.name}</p>
        <p className="text-xs text-slate-muted mb-5">Current stock: <span className="font-mono text-slate-text">{selected.quantity}</span></p>
        <label htmlFor="restock-qty" className="label">Quantity to add</label>
        <input id="restock-qty" type="number" className="input font-mono mb-4" placeholder="0" min="1"
          value={restockQty} onChange={e => setRestockQty(e.target.value)} autoFocus />
        <button onClick={handleRestock} disabled={saving || !restockQty} className="btn-primary w-full">
          {saving ? 'Adding...' : `Add ${restockQty || 0} units`}
        </button>
      </div>
    </div>
  )

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Products</h1>
        <button onClick={() => setView('add')} className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center hover:bg-brand-600 transition-colors flex-shrink-0">
          <Plus size={18} />
        </button>
      </div>

      {requests.length > 0 && (
        <button onClick={() => setShowRequests(true)}
          className="w-full mb-4 flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-left hover:bg-amber-500/15 transition-colors">
          <Clock size={16} className="text-amber-600 dark:text-amber-400 flex-shrink-0" />
          <span className="flex-1 min-w-0 text-sm text-amber-800 dark:text-amber-200">
            {isCashier
              ? `${requests.length} of your deletion ${requests.length === 1 ? 'request is' : 'requests are'} waiting for approval`
              : `${requests.length} product deletion ${requests.length === 1 ? 'request needs' : 'requests need'} your approval`}
          </span>
          <span className="text-xs font-semibold text-amber-800 dark:text-amber-200 underline flex-shrink-0">{isCashier ? 'View' : 'Review'}</span>
        </button>
      )}

      {summary && limits?.maxProductsPerStore != null && (
        <div className="mb-4">
          <UsageLimit label="Products" used={summary.total} limit={limits.maxProductsPerStore} />
        </div>
      )}

      {summary && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div className="card p-3 min-w-0">
            <p className="label mb-1">Total Products</p>
            <p className="stat-number text-lg">{summary.total}</p>
            <p className="text-xs text-slate-dim mt-0.5">All products</p>
          </div>
          <div className="card p-3 min-w-0">
            <p className="label mb-1">Low Stock</p>
            <p className={`stat-number text-lg ${summary.lowStockCount > 0 ? 'text-amber-500' : ''}`}>{summary.lowStockCount}</p>
            <p className="text-xs text-slate-dim mt-0.5">Need restocking</p>
          </div>
          {activeStore?.role !== 'CASHIER' && (
            <>
              <div className="card p-3 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <p className="label mb-0 truncate">Stock Value</p>
                  <button onClick={toggleHideValues} aria-label={hideValues ? 'Show stock value' : 'Hide stock value'} className="text-slate-dim hover:text-slate-text flex-shrink-0">
                    {hideValues ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="stat-number text-base leading-tight break-words">{hideValues ? '••••••' : formatCurrency(summary.totalStockValue)}</p>
              </div>
              <div className="card p-3 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <p className="label mb-0 truncate">Retail Value</p>
                  <button onClick={toggleHideValues} aria-label={hideValues ? 'Show retail value' : 'Hide retail value'} className="text-slate-dim hover:text-slate-text flex-shrink-0">
                    {hideValues ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="stat-number text-base leading-tight break-words">{hideValues ? '••••••' : formatCurrency(summary.totalRetailValue)}</p>
              </div>
            </>
          )}
        </div>
      )}

      <div className="relative mb-2">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-dim" />
        <input className="input pl-9 pr-11" placeholder="Search products by name or scan barcode" value={search} onChange={e => setSearch(e.target.value)} />
        <button onClick={() => setScanningSearch(v => !v)} aria-label={scanningSearch ? 'Stop barcode scan' : 'Scan barcode to search'}
          className={`absolute right-2.5 top-1/2 -translate-y-1/2 ${scanningSearch ? 'text-brand-500' : 'text-slate-dim hover:text-slate-text'}`}>
          <ScanLine size={17} />
        </button>
      </div>

      {scanningSearch && (
        <BarcodeScanner className="mb-4" onDetected={handleSearchScanned} />
      )}

      <div className="mb-4" />

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map(i => <div key={i} className="card h-16 animate-pulse" />)}
        </div>
      ) : products.length === 0 ? (
        <div className="card p-10 text-center">
          <Package size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">{search ? 'No products match your search.' : 'No products yet. Add your first one.'}</p>
        </div>
      ) : (
        <div>
          {truncated && !search && (
            <div className="mb-3 px-4 py-2.5 rounded-lg bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs">
              Showing the first 500 products. Use search to find a specific item.
            </div>
          )}
          <div className="card divide-y divide-navy-700">
          {products.map(product => (
            <div key={product.id} className="px-4 py-3 flex items-center gap-3">
              <ProductAvatar name={product.name} photoUrl={product.photo} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-text truncate">
                  {product.name}
                  {pendingByProduct.has(product.id) && (
                    <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300 align-middle">
                      <Clock size={10} />Deletion pending
                    </span>
                  )}
                </p>
                {product.barcode && <p className="text-xs text-slate-dim font-mono">{product.barcode}</p>}
                <div className="flex gap-3 mt-0.5">
                  {product.cost_price != null && (
                    <span className="text-xs text-slate-dim">Cost <span className="font-mono">{formatCurrency(product.cost_price)}</span></span>
                  )}
                  <span className="text-xs text-slate-dim">Sell <span className="font-mono text-brand-500">{formatCurrency(product.selling_price)}</span></span>
                  <span className="text-xs text-slate-dim">Qty <span className="font-mono">{product.quantity}</span></span>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2 flex-shrink-0">
                {product.is_low_stock && (
                  <span className={`badge ${product.quantity === 0 ? 'badge-danger' : 'badge-warning'}`}>
                    {product.quantity === 0 ? 'Out of stock' : 'Low stock'}
                  </span>
                )}
                {!product.is_low_stock && <span className="badge badge-success">In stock</span>}
                <div className="flex items-center gap-1">
                  <button onClick={() => { setSelected(product); setView('restock') }}
                    className="p-1.5 text-slate-dim hover:text-brand-500 transition-colors" title="Restock">
                    <RefreshCw size={14} />
                  </button>
                  <button onClick={() => { setSelected(product); setView('edit') }}
                    className="p-1.5 text-slate-dim hover:text-slate-text transition-colors">
                    <Edit2 size={14} />
                  </button>
                  <button onClick={() => handleDelete(product)}
                    aria-label={isCashier ? `Request deletion of ${product.name}` : `Delete ${product.name}`}
                    title={isCashier ? (pendingByProduct.has(product.id) ? 'Waiting for approval' : 'Request deletion (needs manager approval)') : 'Delete'}
                    className={`p-1.5 transition-colors ${isCashier && pendingByProduct.has(product.id) ? 'text-slate-dim/40 cursor-not-allowed' : 'text-slate-dim hover:text-red-500'}`}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
          </div>
        </div>
      )}

      {requestFor && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => !sendingRequest && setRequestFor(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="del-req-title" className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <h3 id="del-req-title" className="text-sm font-semibold text-slate-text mb-1">Request deletion</h3>
            <p className="text-xs text-slate-muted mb-4">
              You can't delete <b>{requestFor.name}</b> yourself. Tell your manager why, and they and the owner will be notified. The product is only deleted once one of them approves.
            </p>
            <form onSubmit={submitRequest} className="space-y-3">
              <div>
                <label htmlFor="del-remark" className="label">Reason</label>
                <textarea id="del-remark" className="input min-h-[84px] resize-none" maxLength={300} autoFocus required
                  placeholder="e.g. Added twice by mistake" value={remark} onChange={(e) => setRemark(e.target.value)} />
                <p className="text-[11px] text-slate-dim text-right mt-0.5">{remark.length}/300</p>
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setRequestFor(null)} disabled={sendingRequest} className="btn-ghost flex-1">Cancel</button>
                <button type="submit" disabled={sendingRequest || remark.trim().length < 5} className="btn-primary flex-1">{sendingRequest ? 'Sending...' : 'Send request'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showRequests && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => setShowRequests(false)}>
          <div role="dialog" aria-modal="true" aria-labelledby="del-list-title" className="card w-full sm:max-w-md max-h-[88vh] flex flex-col rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-navy-700">
              <h3 id="del-list-title" className="text-sm font-semibold text-slate-text">{isCashier ? 'Your deletion requests' : 'Deletion requests'}</h3>
              <button onClick={() => setShowRequests(false)} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
            </div>
            <div className="overflow-y-auto divide-y divide-navy-700">
              {requests.length === 0 ? (
                <p className="p-6 text-center text-sm text-slate-muted">Nothing is waiting.</p>
              ) : requests.map((req) => (
                <div key={req.id} className="p-4">
                  <p className="text-sm font-semibold text-slate-text">{req.product_name}</p>
                  <p className="text-xs text-slate-dim mb-2">{isCashier ? 'Sent' : `Requested by ${req.requested_by_name}`} · {formatDateTime(req.created_at)}</p>
                  <p className="text-sm text-slate-text bg-navy-700/40 rounded-lg px-3 py-2 mb-3 break-words">“{req.remark}”</p>
                  {isCashier ? (
                    <button onClick={() => decide(req, 'cancel')} disabled={deciding === req.id} className="btn-ghost w-full text-xs">
                      {deciding === req.id ? 'Cancelling...' : 'Cancel this request'}
                    </button>
                  ) : (
                    <>
                      <input className="input text-sm mb-2" maxLength={300} placeholder="Note to the cashier (optional)" aria-label="Note to the cashier"
                        value={decisionNotes[req.id] || ''} onChange={(e) => setDecisionNotes((n) => ({ ...n, [req.id]: e.target.value }))} />
                      <div className="flex gap-2">
                        <button onClick={() => decide(req, 'reject')} disabled={deciding === req.id} className="btn-ghost flex-1 text-xs">Decline</button>
                        <button onClick={() => setConfirmApprove(req)} disabled={deciding === req.id} className="btn-primary flex-1 text-xs">Approve &amp; delete</button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmApprove}
        title={`Delete \"${confirmApprove?.product_name}\"?`}
        message="Approving permanently deletes this product. This cannot be undone."
        confirmLabel="Approve & delete"
        loading={deciding === confirmApprove?.id}
        onConfirm={() => decide(confirmApprove, 'approve')}
        onCancel={() => setConfirmApprove(null)}
      />

      <ConfirmDialog
        open={!!pendingDelete}
        title={`Delete "${pendingDelete?.name}"?`}
        message="This cannot be undone."
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
