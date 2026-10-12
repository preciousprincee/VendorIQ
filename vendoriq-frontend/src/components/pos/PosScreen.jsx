import { useState, useMemo, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Minus, ChevronLeft, Trash2, Search, ScanLine, UserRound, X, Lock, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { useStore } from '../../context/StoreContext'
import { useAuth } from '../../context/AuthContext'
import { useOffline } from '../../context/OfflineContext'
import { useCatalog } from '../../hooks/useCatalog'
import { useFeatureAccess } from '../../hooks/useFeatureAccess'
import BarcodeScanner from '../scanner/BarcodeScanner'
import { productsForBarcode, sameBarcode } from '../../lib/barcode'
import ReceiptModal from './ReceiptModal'
import CustomerPicker from './CustomerPicker'
import { computeTotals, computePayment, parseMoney, toMoney, newId, METHODS } from '../../lib/offline/money'
import { buildLocalReceipt, receiptFromSale } from '../../lib/offline/receipt'
import { submitSale } from '../../lib/offline/sales'
import { track } from '../../lib/analytics'
import { stampNow } from '../../lib/offline/catalog'
import { formatCurrency, getErrorMessage, formatTime } from '../../lib/utils'

const EMPTY_TENDERS = { CASH: '', TRANSFER: '', CARD: '' }
const SHOWN_PRODUCTS = 60

const roundUp = (n, step) => Math.ceil(n / step) * step
// "Exact", then the next few notes a customer is likely to hand over.
const cashShortcuts = (total) => [...new Set([total, roundUp(total, 100), roundUp(total, 500), roundUp(total, 1000), roundUp(total, 5000)])]
  .filter((v) => v >= total && v > 0).slice(0, 4)

function moneyInput(setter, key) {
  return (e) => setter((t) => ({ ...t, [key]: e.target.value.replace(/[^0-9.,]/g, '') }))
}

export default function PosScreen({ onExit }) {
  const { activeStore } = useStore()
  const { user } = useAuth()
  const { online } = useOffline()
  const { catalog, loaded, reload } = useCatalog(activeStore.id)
  const { requireAccess } = useFeatureAccess('customer_management')

  const [search, setSearch] = useState('')
  const [scanning, setScanning] = useState(false)
  const [cart, setCart] = useState([])
  const [discountType, setDiscountType] = useState('PERCENT')
  const [discountValue, setDiscountValue] = useState('')
  const [customer, setCustomer] = useState(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [paying, setPaying] = useState(false)
  const [mode, setMode] = useState('PAY')
  const [tenders, setTenders] = useState(EMPTY_TENDERS)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(null) // {receipt, status, error, phone}

  const products = catalog?.products || []
  const customersEnabled = !!catalog?.customersEnabled
  const isCashier = activeStore.role === 'CASHIER'
  const maxDiscount = catalog?.maxCashierDiscountPercent ?? 10

  const stockOf = (id) => products.find((p) => p.id === id)?.quantity ?? 0

  const shown = useMemo(() => {
    const q = search.trim().toLowerCase()
    return products
      .filter((p) => p.quantity > 0 && (!q || p.name.toLowerCase().includes(q) || sameBarcode(p.barcode, search)))
      .slice(0, SHOWN_PRODUCTS)
  }, [products, search])

  const totals = useMemo(() => computeTotals(cart, discountType, parseMoney(discountValue) || 0), [cart, discountType, discountValue])
  const discountTooBig = isCashier && totals.discountPercent > maxDiscount + 1e-9
  const discountBad = Number.isNaN(parseMoney(discountValue)) || (discountType === 'PERCENT' && parseMoney(discountValue) > 100)

  const num = (k) => { const v = parseMoney(tenders[k]); return Number.isNaN(v) ? 0 : v }
  const tendersBad = Object.values(tenders).some((t) => Number.isNaN(parseMoney(t)))
  const pay = useMemo(
    () => computePayment(totals.total, { CASH: num('CASH'), TRANSFER: num('TRANSFER'), CARD: num('CARD') }, mode, !!customer),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [totals.total, tenders, mode, customer],
  )

  // The sheet that shows the receipt must not sit on top of a stale open scanner/picker.
  useEffect(() => { if (paying || done) setScanning(false) }, [paying, done])

  const addToCart = (product) => {
    setCart((c) => {
      const existing = c.find((i) => i.productId === product.id)
      if (existing) {
        if (existing.quantity >= product.quantity) { toast.error(`Only ${product.quantity} in stock`); return c }
        return c.map((i) => (i.productId === product.id ? { ...i, quantity: i.quantity + 1 } : i))
      }
      return [...c, { productId: product.id, name: product.name, price: product.selling_price, quantity: 1 }]
    })
  }

  const setQty = (productId, qty) => {
    if (qty <= 0) { setCart((c) => c.filter((i) => i.productId !== productId)); return }
    if (qty > stockOf(productId)) { toast.error(`Only ${stockOf(productId)} in stock`); return }
    setCart((c) => c.map((i) => (i.productId === productId ? { ...i, quantity: qty } : i)))
  }

  // Adds the product with this barcode. Used by the camera and by hardware scanners (which "type" the code
  // and press Enter). Returns true when something was added. A fixed toast id means repeated misses
  // replace each other instead of stacking up.
  const addByBarcode = (code) => {
    const matches = productsForBarcode(products, code)
    if (matches.length === 0) { toast.error('No product matches that barcode', { id: 'scan' }); return false }
    if (matches.length > 1) {
      // Two products share this barcode (old data): don't guess - the wrong item would be sold.
      setSearch(String(code).trim())
      toast.error('More than one product has this barcode - pick the right one from the list', { id: 'scan' })
      return false
    }
    const product = matches[0]
    if (product.quantity <= 0) { toast.error(`${product.name} is out of stock`, { id: 'scan' }); return false }
    const inCart = cart.find((i) => i.productId === product.id)?.quantity || 0
    if (inCart >= product.quantity) { toast.error(`Only ${product.quantity} in stock`, { id: 'scan' }); return false }
    addToCart(product)
    toast.success(`${product.name} added`, { id: 'scan' })
    return true
  }

  const handleScan = (code) => {
    if (addByBarcode(code)) setScanning(false)
  }

  // USB / Bluetooth barcode scanners type the digits into the focused box and press Enter.
  const handleSearchKeyDown = (e) => {
    if (e.key !== 'Enter' || !search.trim()) return
    e.preventDefault()
    if (productsForBarcode(products, search).length > 0 && addByBarcode(search)) setSearch('')
  }

  const openPayment = () => {
    if (cart.length === 0) return
    if (discountBad) { toast.error('Check the discount'); return }
    if (discountTooBig) { toast.error(`A cashier can give up to ${maxDiscount}% off. Ask a manager.`); return }
    setMode('PAY')
    setTenders(EMPTY_TENDERS)
    setPaying(true)
  }

  const resetSale = () => {
    setCart([]); setDiscountValue(''); setCustomer(null); setTenders(EMPTY_TENDERS); setMode('PAY'); setPaying(false)
  }

  const completeSale = async () => {
    if (submitting || !pay.valid || tendersBad) return
    setSubmitting(true)
    const clientId = newId()
    const payload = {
      clientId,
      items: cart.map((i) => ({ productId: i.productId, quantity: i.quantity, unitPrice: toMoney(i.price) })),
      payments: pay.payments,
      // Send what the screen actually applied: a flat discount larger than the
      // subtotal is capped for display, and the server rejects an uncapped one.
      ...(totals.discount > 0 ? { discount: { type: discountType, value: toMoney(discountType === 'PERCENT' ? parseMoney(discountValue) : totals.discount) } } : {}),
      ...(customer ? { customerId: customer.id } : {}),
    }
    const localReceipt = buildLocalReceipt({
      clientId, store: activeStore, cashier: user?.name, createdAt: stampNow(),
      lines: cart, totals, payment: pay, customerName: customer?.name,
    })
    try {
      const result = await submitSale({ store: activeStore, user, payload, receipt: localReceipt, credit: pay.credit })
      track('sale_completed', {
        value: totals.total,
        item_count: cart.reduce((n, i) => n + i.quantity, 0),
        line_count: cart.length,
        payment_methods: [...new Set(pay.payments.map((p) => p.method))],
        offline: result.status !== 'synced',      // queued on the device, not yet on the server
        has_customer: !!customer,
        has_discount: totals.discount > 0,
        on_credit: pay.credit > 0,
      })
      setDone(result.status === 'synced'
        ? { receipt: receiptFromSale(result.sale, activeStore), status: 'synced', phone: customer?.phone }
        : { receipt: localReceipt, status: 'pending', phone: customer?.phone })
      resetSale()
      reload()
    } catch (err) {
      // A real refusal (stock, discount limit, plan...): keep the cart so it can be fixed.
      toast.error(getErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const shift = catalog?.currentShift

  return (
    <div className="p-4 lg:p-6 max-w-5xl animate-fade-in">
      <div className="flex items-center gap-3 mb-4">
        <button onClick={onExit} aria-label="Back to sales" className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text flex-1">New sale</h1>
        <Link to="/shifts" className={`flex items-center gap-1.5 text-xs rounded-full px-3 py-1.5 border ${shift ? 'border-green-500/40 text-green-600 dark:text-green-400' : 'border-navy-600 text-slate-dim'}`}>
          <Clock size={12} />{shift ? `Till open since ${formatTime(shift.opened_at)}` : 'No till session'}
        </Link>
      </div>

      {!loaded ? (
        <div className="card h-40 animate-pulse" />
      ) : !catalog ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-slate-text mb-1">{online ? 'Loading your products...' : 'Your products have not been downloaded to this device yet.'}</p>
          <p className="text-xs text-slate-dim">{online ? 'This only happens the first time.' : 'Connect to the internet once so the till can work offline.'}</p>
          {online && <button onClick={reload} className="btn-ghost text-xs mt-4">Try again</button>}
        </div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-4">
          {/* ---- pick products ---- */}
          <div>
            <div className="flex gap-2 mb-3">
              <div className="relative flex-1">
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-dim" />
                <input className="input pl-9" placeholder="Search or type a barcode..." value={search} onChange={(e) => setSearch(e.target.value)} onKeyDown={handleSearchKeyDown} />
              </div>
              <button type="button" onClick={() => setScanning((v) => !v)} aria-label={scanning ? 'Stop barcode scan' : 'Scan barcode'}
                className={`flex-shrink-0 px-3 rounded-xl border transition-colors ${scanning ? 'border-brand-500 text-brand-500' : 'border-navy-600 text-slate-muted hover:text-slate-text hover:border-navy-500'}`}>
                <ScanLine size={18} />
              </button>
            </div>
            {scanning && (
              <div className="mb-3">
                <BarcodeScanner onDetected={handleScan} />
                <p className="mt-1.5 text-center text-xs text-slate-dim">Point the camera at the product's barcode</p>
              </div>
            )}
            <div className="card divide-y divide-navy-700 max-h-72 lg:max-h-[28rem] overflow-y-auto">
              {shown.length === 0 ? (
                <p className="p-4 text-sm text-slate-muted text-center">{products.length === 0 ? 'No products yet - add some on the Products page.' : 'No products found'}</p>
              ) : shown.map((p) => (
                <button key={p.id} onClick={() => addToCart(p)} className="w-full px-4 py-3 text-left hover:bg-navy-700/50 transition-colors flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm text-slate-text truncate">{p.name}</p>
                    <p className="text-xs text-slate-dim font-mono">{formatCurrency(p.selling_price)} · {p.quantity} in stock</p>
                  </div>
                  <div className="w-7 h-7 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center text-brand-500 flex-shrink-0"><Plus size={14} /></div>
                </button>
              ))}
            </div>
          </div>

          {/* ---- cart ---- */}
          <div>
            <p className="label mb-2">Cart</p>
            {cart.length === 0 ? (
              <div className="card p-8 text-center text-sm text-slate-muted">Tap a product to add it</div>
            ) : (
              <div className="card divide-y divide-navy-700 mb-3">
                {cart.map((item) => (
                  <div key={item.productId} className="px-4 py-3 flex items-center gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-text truncate">{item.name}</p>
                      <p className="text-xs text-brand-500 font-mono">{formatCurrency(item.price)} each</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => setQty(item.productId, item.quantity - 1)} aria-label="Decrease" className="w-7 h-7 rounded-full bg-navy-700 text-slate-text flex items-center justify-center hover:bg-navy-600"><Minus size={13} /></button>
                      <span className="font-mono text-sm w-6 text-center">{item.quantity}</span>
                      <button onClick={() => setQty(item.productId, item.quantity + 1)} aria-label="Increase" className="w-7 h-7 rounded-full bg-navy-700 text-slate-text flex items-center justify-center hover:bg-navy-600"><Plus size={13} /></button>
                      <button onClick={() => setCart((c) => c.filter((i) => i.productId !== item.productId))} aria-label={`Remove ${item.name}`} className="text-slate-dim hover:text-red-500 dark:hover:text-red-400 ml-1"><Trash2 size={14} /></button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {cart.length > 0 && (
              <>
                <div className="card p-3 mb-3 space-y-3">
                  <div>
                    <label htmlFor="pos-discount" className="label">Discount <span className="text-slate-dim normal-case">{isCashier ? `(up to ${maxDiscount}%)` : '(optional)'}</span></label>
                    <div className="flex gap-2">
                      <div className="flex rounded-xl border border-navy-600 overflow-hidden flex-shrink-0">
                        {[['PERCENT', '%'], ['AMOUNT', '\u20a6']].map(([key, label]) => (
                          <button key={key} type="button" onClick={() => setDiscountType(key)}
                            className={`px-3 text-sm ${discountType === key ? 'bg-brand-500 text-white' : 'text-slate-muted hover:text-slate-text'}`}>{label}</button>
                        ))}
                      </div>
                      <input id="pos-discount" className="input font-mono" inputMode="decimal" placeholder="0" value={discountValue}
                        onChange={(e) => setDiscountValue(e.target.value.replace(/[^0-9.,]/g, ''))} />
                    </div>
                    {discountTooBig && <p className="text-xs text-red-500 dark:text-red-400 mt-1">Above the {maxDiscount}% a cashier may give - ask a manager.</p>}
                    {discountBad && <p className="text-xs text-red-500 dark:text-red-400 mt-1">Enter a valid discount.</p>}
                  </div>

                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs text-slate-dim">Customer</p>
                    {customer ? (
                      <span className="flex items-center gap-1.5 text-sm text-slate-text">
                        <UserRound size={14} />{customer.name}
                        <button onClick={() => setCustomer(null)} aria-label="Remove customer" className="text-slate-dim hover:text-red-500"><X size={14} /></button>
                      </span>
                    ) : customersEnabled ? (
                      <button onClick={() => setPickerOpen(true)} className="text-xs text-brand-500 hover:underline">Choose customer</button>
                    ) : (
                      <button onClick={() => requireAccess()} className="flex items-center gap-1 text-xs text-slate-dim hover:text-brand-500"><Lock size={12} />Customers & credit (Pro)</button>
                    )}
                  </div>
                </div>

                <div className="card p-4 mb-3 space-y-1.5 text-sm">
                  {totals.discount > 0 && (
                    <>
                      <div className="flex justify-between text-slate-muted"><span>Subtotal</span><span className="font-mono">{formatCurrency(totals.subtotal)}</span></div>
                      <div className="flex justify-between text-slate-muted"><span>Discount</span><span className="font-mono">-{formatCurrency(totals.discount)}</span></div>
                    </>
                  )}
                  <div className="flex justify-between font-semibold text-slate-text"><span>Total</span><span className="font-mono text-brand-500 text-base">{formatCurrency(totals.total)}</span></div>
                </div>

                <button onClick={openPayment} disabled={discountBad || discountTooBig} className="btn-primary w-full">
                  Charge {formatCurrency(totals.total)}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {paying && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => !submitting && setPaying(false)}>
          <div role="dialog" aria-modal="true" aria-label="Payment" className="card w-full sm:max-w-sm max-h-[92vh] overflow-y-auto p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-semibold text-slate-text">Payment</h3>
              <button onClick={() => setPaying(false)} disabled={submitting} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
            </div>
            <p className="text-3xl font-bold font-mono text-brand-500 mb-4">{formatCurrency(totals.total)}</p>

            <div className="flex rounded-xl border border-navy-600 overflow-hidden mb-4 text-sm">
              <button type="button" onClick={() => setMode('PAY')} className={`flex-1 py-2 ${mode === 'PAY' ? 'bg-brand-500 text-white' : 'text-slate-muted'}`}>Pay now</button>
              <button type="button" onClick={() => (customersEnabled ? setMode('CREDIT') : requireAccess())}
                className={`flex-1 py-2 flex items-center justify-center gap-1 ${mode === 'CREDIT' ? 'bg-brand-500 text-white' : 'text-slate-muted'}`}>
                {!customersEnabled && <Lock size={12} />}On credit
              </button>
            </div>

            {mode === 'CREDIT' && (
              <div className="flex items-center justify-between mb-3 text-sm">
                <span className="text-slate-dim">Customer</span>
                {customer ? <span className="text-slate-text">{customer.name}</span>
                  : <button onClick={() => setPickerOpen(true)} className="text-brand-500 text-xs hover:underline">Choose customer</button>}
              </div>
            )}

            <div className="space-y-3">
              {METHODS.map(({ key, label }) => (
                <div key={key}>
                  <label htmlFor={`tender-${key}`} className="label">{label}{key === 'CASH' ? ' received' : ''}</label>
                  <input id={`tender-${key}`} className="input font-mono" inputMode="decimal" placeholder={mode === 'PAY' && key === 'CASH' ? `${totals.total} (exact)` : '0'}
                    value={tenders[key]} onChange={moneyInput(setTenders, key)} />
                  {key === 'CASH' && mode === 'PAY' && (
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {cashShortcuts(totals.total).map((v) => (
                        <button key={v} type="button" onClick={() => setTenders((t) => ({ ...t, CASH: String(v) }))}
                          className="text-xs px-2.5 py-1 rounded-full border border-navy-600 text-slate-muted hover:text-slate-text hover:border-navy-500 font-mono">
                          {v === totals.total ? 'Exact' : formatCurrency(v)}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="mt-4 space-y-1 text-sm">
              {pay.change > 0 && <div className="flex justify-between text-green-600 dark:text-green-400 font-semibold"><span>Change to give</span><span className="font-mono">{formatCurrency(pay.change)}</span></div>}
              {pay.credit > 0 && mode === 'CREDIT' && <div className="flex justify-between text-amber-600 dark:text-amber-400 font-semibold"><span>On credit</span><span className="font-mono">{formatCurrency(pay.credit)}</span></div>}
              {(tendersBad || pay.error) && <p role="alert" className="text-xs text-red-500 dark:text-red-400">{tendersBad ? 'Enter valid amounts.' : pay.error}</p>}
            </div>

            <button onClick={completeSale} disabled={submitting || !pay.valid || tendersBad} className="btn-primary w-full mt-4">
              {submitting ? 'Saving...' : mode === 'CREDIT' ? 'Record credit sale' : pay.exact ? `Complete \u00b7 cash ${formatCurrency(totals.total)}` : 'Complete sale'}
            </button>
            {!online && <p className="text-[11px] text-center text-slate-dim mt-2">Offline - this sale will be saved on the device and synced later.</p>}
          </div>
        </div>
      )}

      {pickerOpen && (
        <CustomerPicker
          storeId={activeStore.id}
          customers={catalog?.customers || []}
          onPick={(c) => { setCustomer(c); setPickerOpen(false) }}
          onCreated={() => reload()}
          onClose={() => setPickerOpen(false)}
        />
      )}

      {done && (
        <ReceiptModal
          receipt={done.receipt}
          syncStatus={done.status}
          customerPhone={done.phone}
          onClose={() => { setDone(null); onExit() }}
          primary={{ label: 'New sale', onClick: () => setDone(null) }}
        />
      )}
    </div>
  )
}
