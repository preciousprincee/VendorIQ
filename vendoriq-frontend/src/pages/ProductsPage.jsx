import { useState, useEffect, useRef } from 'react'
import { Plus, Search, ScanLine, Edit2, Trash2, Package, RefreshCw, Eye, EyeOff, ChevronLeft } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useSubscription } from '../context/SubscriptionContext'
import UsageLimit from '../components/billing/UsageLimit'
import api from '../lib/api'
import { formatCurrency, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

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

function ProductForm({ initial = EMPTY_FORM, onSave, onCancel, loading }) {
  const [form, setForm] = useState(initial)
  const [scanning, setScanning] = useState(false)
  const videoRef = useRef(null)
  const scannerRef = useRef(null)
  const photoInputRef = useRef(null)

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const handlePhotoChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { toast.error('Please choose an image file'); return }
    if (file.size > 5 * 1024 * 1024) { toast.error('Image must be under 5MB'); return }
    setForm(f => ({ ...f, photo: file, photoPreview: URL.createObjectURL(file), removePhoto: false }))
  }

  const removePhoto = () => {
    setForm(f => ({ ...f, photo: null, photoPreview: null, removePhoto: true }))
    if (photoInputRef.current) photoInputRef.current.value = ''
  }

  const startScan = async () => {
    try {
      const { BrowserMultiFormatReader } = await import('@zxing/browser')
      const reader = new BrowserMultiFormatReader()
      scannerRef.current = reader
      setScanning(true)
      await reader.decodeFromVideoDevice(undefined, videoRef.current, (result) => {
        if (result) {
          setForm(f => ({ ...f, barcode: result.getText() }))
          stopScan()
          toast.success('Barcode scanned')
        }
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

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave({
      name: form.name,
      barcode: form.barcode || undefined,
      cost_price: Number(form.cost_price),
      selling_price: Number(form.selling_price),
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
                Upload photo
              </label>
              {(form.photoPreview || (!form.removePhoto && form.existingPhotoUrl)) && (
                <button type="button" onClick={removePhoto} className="text-xs text-red-500 dark:text-red-400 hover:underline">
                  Remove
                </button>
              )}
            </div>
            <p className="text-xs text-slate-dim">Without a photo, products show an initial instead.</p>
          </div>
        </div>
      </div>

      <div>
        <label className="label">Product name</label>
        <input className="input" placeholder="e.g. Indomie Noodles (70g)" value={form.name} onChange={set('name')} required />
      </div>

      <div>
        <label className="label">Barcode <span className="text-slate-dim normal-case">(optional)</span></label>
        <div className="flex gap-2">
          <input className="input" placeholder="Scan or enter manually" value={form.barcode} onChange={set('barcode')} />
          <button type="button" onClick={scanning ? stopScan : startScan}
            className={`flex-shrink-0 px-3 rounded-xl border transition-colors ${scanning ? 'border-brand-500 text-brand-500' : 'border-navy-600 text-slate-muted hover:text-slate-text hover:border-navy-500'}`}>
            <ScanLine size={18} />
          </button>
        </div>
        {scanning && (
          <div className="mt-2 relative rounded-xl overflow-hidden bg-black aspect-video">
            <video ref={videoRef} className="w-full h-full object-cover" />
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-48 h-24 border-2 border-brand-500 rounded opacity-70" />
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Cost price (₦)</label>
          <input type="number" className="input font-mono" placeholder="0" min="0" step="0.01"
            value={form.cost_price} onChange={set('cost_price')} required />
        </div>
        <div>
          <label className="label">Selling price (₦)</label>
          <input type="number" className="input font-mono" placeholder="0" min="0" step="0.01"
            value={form.selling_price} onChange={set('selling_price')} required />
        </div>
      </div>

      {margin !== null && (
        <p className="text-xs text-slate-muted">
          Margin: <span className={`font-mono font-medium ${Number(margin) > 0 ? 'text-brand-500' : 'text-red-500 dark:text-red-400'}`}>{margin}%</span>
        </p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Quantity in stock</label>
          <input type="number" className="input font-mono" placeholder="0" min="0"
            value={form.quantity} onChange={set('quantity')} required />
        </div>
        <div>
          <label className="label">Low stock alert at</label>
          <input type="number" className="input font-mono" placeholder="5" min="0"
            value={form.low_stock_threshold} onChange={set('low_stock_threshold')} />
        </div>
      </div>
      <p className="text-xs text-slate-dim -mt-2">You'll be alerted when stock falls below this.</p>

      <div>
        <label className="label">Category <span className="text-slate-dim normal-case">(optional)</span></label>
        <input className="input" list="category-suggestions" placeholder="e.g. Cooking Oil" value={form.category} onChange={set('category')} />
        <datalist id="category-suggestions">
          {CATEGORY_SUGGESTIONS.map(c => <option key={c} value={c} />)}
        </datalist>
      </div>

      <div>
        <label className="label">Supplier <span className="text-slate-dim normal-case">(optional)</span></label>
        <input className="input" placeholder="e.g. PZ Cussons" value={form.supplier} onChange={set('supplier')} />
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
  const [search, setSearch] = useState('')
  const [view, setView] = useState('list') // list | add | edit | restock
  const [selected, setSelected] = useState(null)
  const [restockQty, setRestockQty] = useState('')
  const [scanningSearch, setScanningSearch] = useState(false)
  const [hideValues, setHideValues] = useState(() => localStorage.getItem('viq_hide_stock_value') === 'true')
  const searchVideoRef = useRef(null)
  const searchScannerRef = useRef(null)

  // Camera cleanup on unmount - the explicit "stop scan" actions already
  // release these, but nothing released either camera if the user
  // navigates away mid-scan instead (a nav tap, browser back, switching
  // stores). Without this, whichever scanner was active keeps running in
  // the background indefinitely - the camera indicator light stays on and
  // decoding keeps burning battery/CPU, which matters on the mobile POS
  // use case this page is built for, where moving between screens
  // mid-shift without remembering to stop scanning first is the normal
  // case, not an edge case. Two separate scanners here (restock barcode
  // scan vs. search-by-barcode scan), so both refs need releasing.
  useEffect(() => {
    return () => {
      scannerRef.current?.reset()
      searchScannerRef.current?.reset()
    }
  }, [])

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

  const startSearchScan = async () => {
    try {
      const { BrowserMultiFormatReader } = await import('@zxing/browser')
      const reader = new BrowserMultiFormatReader()
      searchScannerRef.current = reader
      setScanningSearch(true)
      await reader.decodeFromVideoDevice(undefined, searchVideoRef.current, (result) => {
        if (result) {
          setSearch(result.getText())
          stopSearchScan()
        }
      })
    } catch {
      toast.error('Camera not available')
      setScanningSearch(false)
    }
  }
  const stopSearchScan = () => {
    searchScannerRef.current?.reset()
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

  const handleDelete = async (product) => {
    if (!confirm(`Delete "${product.name}"? This cannot be undone.`)) return
    try {
      await api.delete(`/stores/${activeStore.id}/products/${product.id}/`)
      toast.success('Product deleted')
      fetchProducts()
    } catch (err) {
      toast.error(getErrorMessage(err))
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
        <label className="label">Quantity to add</label>
        <input type="number" className="input font-mono mb-4" placeholder="0" min="1"
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
                  <button onClick={toggleHideValues} className="text-slate-dim hover:text-slate-text flex-shrink-0">
                    {hideValues ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                <p className="stat-number text-base leading-tight break-words">{hideValues ? '••••••' : formatCurrency(summary.totalStockValue)}</p>
              </div>
              <div className="card p-3 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <p className="label mb-0 truncate">Retail Value</p>
                  <button onClick={toggleHideValues} className="text-slate-dim hover:text-slate-text flex-shrink-0">
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
        <button onClick={scanningSearch ? stopSearchScan : startSearchScan}
          className={`absolute right-2.5 top-1/2 -translate-y-1/2 ${scanningSearch ? 'text-brand-500' : 'text-slate-dim hover:text-slate-text'}`}>
          <ScanLine size={17} />
        </button>
      </div>

      {scanningSearch && (
        <div className="mb-4 relative rounded-xl overflow-hidden bg-black aspect-video">
          <video ref={searchVideoRef} className="w-full h-full object-cover" />
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-48 h-24 border-2 border-brand-500 rounded opacity-70" />
          </div>
        </div>
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
                <p className="text-sm font-medium text-slate-text truncate">{product.name}</p>
                {product.barcode && <p className="text-xs text-slate-dim font-mono">{product.barcode}</p>}
                <div className="flex gap-3 mt-0.5">
                  <span className="text-xs text-slate-dim">Cost <span className="font-mono">{formatCurrency(product.cost_price)}</span></span>
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
                    className="p-1.5 text-slate-dim hover:text-red-500 transition-colors">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
          </div>
        </div>
      )}
    </div>
  )
}
