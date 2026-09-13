import { useState, useEffect, useRef } from 'react'
import { Plus, ChevronLeft, Trash2, FileText, Search, CheckCircle, Send, Clock, User, Mail, MessageCircle, Share2, Copy, X } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useFeatureAccess } from '../hooks/useFeatureAccess'
import api from '../lib/api'
import { formatCurrency, formatDate, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'
import ConfirmDialog from '../components/ConfirmDialog'

const STATUS_META = {
  DRAFT: { label: 'Draft', color: 'text-slate-dim', badge: 'badge', icon: Clock },
  SENT: { label: 'Sent', color: 'text-blue-500 dark:text-blue-400', badge: 'badge bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400', icon: Send },
  PAID: { label: 'Paid', color: 'text-brand-500', badge: 'badge-success', icon: CheckCircle },
}

// WhatsApp/SMS need a plain digit string with country code, no spaces/dashes/+.
// Best-effort only: assumes an 11-digit local number starting with 0 is
// Nigerian (this app's primary market) and swaps the leading 0 for 234.
// A number that's already in some other valid international format just
// passes through digit-stripped, which may not always be correct - there's
// no way to know a phone's country for certain from the digits alone.
function toIntlDigits(phone) {
  const digits = (phone || '').replace(/\D/g, '')
  if (digits.startsWith('0') && digits.length === 11) return '234' + digits.slice(1)
  return digits
}

function buildInvoiceMessage(invoice, storeName) {
  const lines = [
    `Invoice from ${storeName}`,
    '',
    ...(invoice.invoice_items || []).map(item =>
      `${item.product?.name || 'Item'} x${item.quantity} - ${formatCurrency(item.unit_price * item.quantity)}`
    ),
    '',
    `Total: ${formatCurrency(invoice.total_amount)}`,
    `Status: ${STATUS_META[invoice.status]?.label || invoice.status}`,
    '',
    'Thank you for your business!',
  ]
  return lines.join('\n')
}

export default function InvoicesPage() {
  const { activeStore } = useStore()
  const { requireAccess: requireInvoicing } = useFeatureAccess('invoicing')
  const [invoices, setInvoices] = useState([])
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const fetchInvoicesRef = useRef(0)
  const [view, setView] = useState('list') // list | new | detail
  const [selected, setSelected] = useState(null)
  const [sending, setSending] = useState(false)
  const [sendModalInvoice, setSendModalInvoice] = useState(null)
  const [emailPromptInvoice, setEmailPromptInvoice] = useState(null)
  const [emailInput, setEmailInput] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [pendingDeleteInvoice, setPendingDeleteInvoice] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [form, setForm] = useState({ customerName: '', customerEmail: '', customerPhone: '', items: [] })

  const fetchInvoices = async () => {
    // Same request-counter guard as ProductsPage - switching status
    // filter tabs quickly can let an older filter's response resolve
    // after a newer one, silently showing e.g. "Paid" invoices while the
    // tab still reads "Overdue".
    const requestId = ++fetchInvoicesRef.current
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/invoices/`, {
        params: statusFilter ? { status: statusFilter } : {}
      })
      if (requestId !== fetchInvoicesRef.current) return
      setInvoices(data.invoices)
    } catch (err) {
      if (requestId === fetchInvoicesRef.current) toast.error(getErrorMessage(err))
    } finally {
      if (requestId === fetchInvoicesRef.current) setLoading(false)
    }
  }

  const fetchProducts = async () => {
    const { data } = await api.get(`/stores/${activeStore.id}/products/`)
    setProducts(data.products)
  }

  useEffect(() => { if (activeStore) fetchInvoices() }, [activeStore, statusFilter])

  const openNew = async () => {
    if (!requireInvoicing()) return
    await fetchProducts()
    setForm({ customerName: '', customerEmail: '', customerPhone: '', items: [] })
    setView('new')
  }

  const addItem = (product) => {
    setForm(f => {
      const existing = f.items.find(i => i.productId === product.id)
      if (existing) return { ...f, items: f.items.map(i => i.productId === product.id ? { ...i, quantity: i.quantity + 1 } : i) }
      return { ...f, items: [...f.items, { productId: product.id, name: product.name, unitPrice: Number(product.selling_price), quantity: 1 }] }
    })
  }

  const updateItem = (productId, key, value) => {
    setForm(f => ({ ...f, items: f.items.map(i => i.productId === productId ? { ...i, [key]: value } : i) }))
  }

  const removeItem = (productId) => {
    setForm(f => ({ ...f, items: f.items.filter(i => i.productId !== productId) }))
  }

  const invoiceTotal = form.items.reduce((s, i) => s + i.unitPrice * i.quantity, 0)

  const handleCreate = async (e) => {
    e.preventDefault()
    if (form.items.length === 0) { toast.error('Add at least one item'); return }
    setSaving(true)
    try {
      await api.post(`/stores/${activeStore.id}/invoices/`, {
        customerName: form.customerName,
        customerEmail: form.customerEmail || undefined,
        customerPhone: form.customerPhone || undefined,
        items: form.items.map(i => ({ productId: i.productId, quantity: i.quantity, unitPrice: i.unitPrice }))
      })
      toast.success('Invoice created')
      setView('list')
      fetchInvoices()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleStatusUpdate = async (invoiceId, status) => {
    try {
      await api.patch(`/stores/${activeStore.id}/invoices/${invoiceId}/status/`, { status })
      toast.success(`Marked as ${STATUS_META[status].label}`)
      fetchInvoices()
      if (selected?.id === invoiceId) setSelected(prev => ({ ...prev, status }))
    } catch (err) {
      toast.error(getErrorMessage(err))
    }
  }

  const sendViaEmail = async (invoice, email) => {
    setSending(true)
    try {
      const { data } = await api.post(`/stores/${activeStore.id}/invoices/${invoice.id}/send/`, { email })
      toast.success(data.message || 'Invoice sent')
      fetchInvoices()
      if (selected?.id === invoice.id) setSelected(data.invoice)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSending(false)
    }
  }

  const handleSendEmail = (invoice) => {
    setSendModalInvoice(null)
    if (invoice.customer_email) {
      sendViaEmail(invoice, invoice.customer_email)
    } else {
      setEmailInput('')
      setEmailPromptInvoice(invoice)
    }
  }

  const handleConfirmEmailPrompt = () => {
    if (!emailInput.trim()) return
    const invoice = emailPromptInvoice
    setEmailPromptInvoice(null)
    sendViaEmail(invoice, emailInput.trim())
  }

  const handleSendWhatsApp = (invoice) => {
    if (!invoice.customer_phone) {
      toast.error('No phone number on file for this customer.')
      return
    }
    const digits = toIntlDigits(invoice.customer_phone)
    const text = encodeURIComponent(buildInvoiceMessage(invoice, activeStore.name))
    // wa.me opens WhatsApp (app or web) with the message pre-filled - the
    // person still has to tap send themselves. There's no automated-sending
    // API wired up here (that needs a paid WhatsApp Business API provider
    // like Twilio or Meta's Cloud API, plus business verification) - this
    // is the zero-setup option that works today.
    window.open(`https://wa.me/${digits}?text=${text}`, '_blank')
    setSendModalInvoice(null)
  }

  const handleSendSMS = (invoice) => {
    if (!invoice.customer_phone) {
      toast.error('No phone number on file for this customer.')
      return
    }
    const text = encodeURIComponent(buildInvoiceMessage(invoice, activeStore.name))
    // sms: URI scheme opens the phone's native messaging app pre-filled.
    // Only works when opened from an actual phone (mobile Safari/Chrome) -
    // desktop browsers have nothing to hand this off to.
    window.location.href = `sms:${invoice.customer_phone}?body=${text}`
    setSendModalInvoice(null)
  }

  const handleNativeShare = async (invoice) => {
    const text = buildInvoiceMessage(invoice, activeStore.name)
    try {
      await navigator.share({ title: `Invoice from ${activeStore.name}`, text })
      setSendModalInvoice(null)
    } catch (err) {
      // User cancelled the share sheet - not an error, just close nothing.
      if (err?.name !== 'AbortError') toast.error('Could not open share sheet.')
    }
  }

  const handleCopyText = async (invoice) => {
    const text = buildInvoiceMessage(invoice, activeStore.name)
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Invoice details copied to clipboard')
      setSendModalInvoice(null)
    } catch {
      toast.error('Could not copy to clipboard.')
    }
  }

  const handleDelete = async () => {
    const invoice = pendingDeleteInvoice
    setDeleting(true)
    try {
      await api.delete(`/stores/${activeStore.id}/invoices/${invoice.id}/`)
      toast.success('Invoice deleted')
      setPendingDeleteInvoice(null)
      setView('list')
      fetchInvoices()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeleting(false)
    }
  }

  const handlePrint = (invoice) => {
    const win = window.open('', '_blank')
    const store = activeStore
    win.document.write(`
      <html><head><title>Invoice - ${invoice.customer_name}</title>
      <style>
        body { font-family: 'Inter', sans-serif; padding: 40px; color: #1a1a1a; max-width: 600px; margin: 0 auto; }
        h1 { font-size: 24px; margin: 0; } .header { display: flex; justify-content: space-between; margin-bottom: 40px; }
        .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #888; margin-bottom: 4px; }
        .value { font-size: 14px; font-weight: 500; }
        table { width: 100%; border-collapse: collapse; margin: 24px 0; }
        th { text-align: left; font-size: 11px; text-transform: uppercase; color: #888; padding: 8px 0; border-bottom: 1px solid #eee; }
        td { padding: 12px 0; border-bottom: 1px solid #f5f5f5; font-size: 14px; }
        .total-row td { font-weight: 700; font-size: 16px; border-bottom: none; padding-top: 16px; }
        .badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
          background: ${invoice.status === 'PAID' ? '#dcfce7' : invoice.status === 'SENT' ? '#dbeafe' : '#f3f4f6'};
          color: ${invoice.status === 'PAID' ? '#16a34a' : invoice.status === 'SENT' ? '#2563eb' : '#6b7280'}; }
      </style></head><body>
      <div class="header">
        <div><h1>${store.name}</h1>${store.location ? `<p style="color:#888;margin-top:4px">${store.location}</p>` : ''}</div>
        <div style="text-align:right"><div class="badge">${invoice.status}</div><p style="color:#888;font-size:13px;margin-top:8px">${formatDate(invoice.created_at)}</p></div>
      </div>
      <div style="margin-bottom:32px">
        <div class="label">Bill to</div>
        <div class="value">${invoice.customer_name}</div>
        ${invoice.customer_email ? `<div style="color:#888;font-size:13px">${invoice.customer_email}</div>` : ''}
        ${invoice.customer_phone ? `<div style="color:#888;font-size:13px">${invoice.customer_phone}</div>` : ''}
      </div>
      <table>
        <thead><tr><th>Item</th><th style="text-align:right">Qty</th><th style="text-align:right">Price</th><th style="text-align:right">Total</th></tr></thead>
        <tbody>
          ${invoice.invoice_items.map(item => `
            <tr>
              <td>${item.product?.name || 'Product'}</td>
              <td style="text-align:right">${item.quantity}</td>
              <td style="text-align:right">${formatCurrency(item.unit_price)}</td>
              <td style="text-align:right">${formatCurrency(Number(item.unit_price) * item.quantity)}</td>
            </tr>`).join('')}
          <tr class="total-row"><td colspan="3">Total</td><td style="text-align:right">${formatCurrency(invoice.total_amount)}</td></tr>
        </tbody>
      </table>
      <p style="color:#888;font-size:12px;margin-top:40px;text-align:center">Generated by VendorIQ</p>
      </body></html>`)
    win.document.close()
    win.print()
  }

  // --- New invoice view ---
  if (view === 'new') return (
    <div className="p-5 max-w-xl animate-fade-in">
      <div className="flex items-center gap-3 mb-5">
        <button onClick={() => setView('list')} className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">New invoice</h1>
      </div>
      <form onSubmit={handleCreate} className="space-y-5">
        <div className="card p-4 space-y-3">
          <p className="text-xs font-semibold text-slate-muted uppercase tracking-wider">Customer details</p>
          <div>
            <label className="label">Customer name</label>
            <input className="input" placeholder="e.g. Ade Supermarket" value={form.customerName}
              onChange={e => setForm(f => ({ ...f, customerName: e.target.value }))} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Email <span className="text-slate-dim normal-case">(optional)</span></label>
              <input type="email" className="input" placeholder="ade@example.com" value={form.customerEmail}
                onChange={e => setForm(f => ({ ...f, customerEmail: e.target.value }))} />
            </div>
            <div>
              <label className="label">Phone <span className="text-slate-dim normal-case">(optional)</span></label>
              <input type="tel" className="input" placeholder="+234..." value={form.customerPhone}
                onChange={e => setForm(f => ({ ...f, customerPhone: e.target.value }))} />
            </div>
          </div>
        </div>

        <div>
          <p className="label mb-2">Add items</p>
          <div className="card max-h-44 overflow-y-auto divide-y divide-navy-700">
            {products.map(p => (
              <button type="button" key={p.id} onClick={() => addItem(p)}
                className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-navy-700/50 transition-colors text-left">
                <span className="text-sm text-slate-text">{p.name}</span>
                <span className="text-xs font-mono text-brand-500">{formatCurrency(p.selling_price)}</span>
              </button>
            ))}
          </div>
        </div>

        {form.items.length > 0 && (
          <div>
            <p className="label mb-2">Invoice items</p>
            <div className="card divide-y divide-navy-700">
              {form.items.map(item => (
                <div key={item.productId} className="px-4 py-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-text truncate">{item.name}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-slate-dim">Price:</span>
                      <input type="number" className="input py-1 px-2 w-24 text-xs font-mono" min="0" step="0.01"
                        value={item.unitPrice} onChange={e => updateItem(item.productId, 'unitPrice', Number(e.target.value))} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button type="button" onClick={() => updateItem(item.productId, 'quantity', Math.max(1, item.quantity - 1))}
                      className="w-7 h-7 rounded bg-navy-700 text-slate-text flex items-center justify-center hover:bg-navy-600">−</button>
                    <span className="font-mono text-sm w-5 text-center">{item.quantity}</span>
                    <button type="button" onClick={() => updateItem(item.productId, 'quantity', item.quantity + 1)}
                      className="w-7 h-7 rounded bg-navy-700 text-slate-text flex items-center justify-center hover:bg-navy-600">+</button>
                    <button type="button" onClick={() => removeItem(item.productId)} className="text-slate-dim hover:text-red-500 dark:hover:text-red-400 ml-1">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
              <div className="px-4 py-3 flex justify-between">
                <span className="text-sm font-semibold text-slate-text">Total</span>
                <span className="font-mono font-semibold text-brand-500">{formatCurrency(invoiceTotal)}</span>
              </div>
            </div>
          </div>
        )}

        <button type="submit" disabled={saving} className="btn-primary w-full">
          {saving ? 'Creating...' : 'Create invoice'}
        </button>
      </form>
    </div>
  )

  // --- Invoice detail view ---
  if (view === 'detail' && selected) return (
    <div className="p-5 max-w-xl animate-fade-in">
      <div className="flex items-center gap-3 mb-5">
        <button onClick={() => { setView('list'); setSelected(null) }} className="text-slate-muted hover:text-slate-text"><ChevronLeft size={20} /></button>
        <h1 className="text-lg font-bold text-slate-text">Invoice</h1>
        <span className={`badge ${STATUS_META[selected.status]?.badge}`}>{STATUS_META[selected.status]?.label}</span>
      </div>

      <div className="card p-5 mb-4">
        <p className="label mb-1">Customer</p>
        <p className="text-sm font-semibold text-slate-text">{selected.customer_name}</p>
        {selected.customer_email && <p className="text-xs text-slate-dim mt-0.5">{selected.customer_email}</p>}
        {selected.customer_phone && <p className="text-xs text-slate-dim">{selected.customer_phone}</p>}
        <p className="text-xs text-slate-dim mt-2">Created {formatDate(selected.created_at)}</p>
      </div>

      <div className="card divide-y divide-navy-700 mb-4">
        {selected.invoice_items?.map(item => (
          <div key={item.id} className="px-4 py-3 flex justify-between items-center">
            <div>
              <p className="text-sm text-slate-text">{item.product?.name}</p>
              <p className="text-xs text-slate-dim font-mono">{formatCurrency(item.unit_price)} × {item.quantity}</p>
            </div>
            <p className="font-mono text-sm text-slate-text">{formatCurrency(Number(item.unit_price) * item.quantity)}</p>
          </div>
        ))}
        <div className="px-4 py-3 flex justify-between">
          <span className="font-semibold text-slate-text">Total</span>
          <span className="font-mono font-bold text-brand-500">{formatCurrency(selected.total_amount)}</span>
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        <button onClick={() => setSendModalInvoice(selected)} disabled={sending} className="btn-ghost text-sm flex items-center gap-1.5">
          <Send size={14} />{sending ? 'Sending...' : selected.status === 'DRAFT' ? 'Send invoice' : 'Resend invoice'}
        </button>
        {selected.status !== 'PAID' && (
          <button onClick={() => handleStatusUpdate(selected.id, 'PAID')} className="btn-ghost text-sm text-brand-500 flex items-center gap-1.5">
            <CheckCircle size={14} />Mark as Paid
          </button>
        )}
        <button onClick={() => handlePrint(selected)} className="btn-primary text-sm flex items-center gap-1.5">
          <FileText size={14} />Print / Save PDF
        </button>
        <button onClick={() => setPendingDeleteInvoice(selected)} className="btn-danger text-sm flex items-center gap-1.5">
          <Trash2 size={14} />Delete
        </button>
      </div>

      <ConfirmDialog
        open={!!pendingDeleteInvoice}
        title="Delete this invoice?"
        message={pendingDeleteInvoice ? `This will permanently delete the invoice for ${pendingDeleteInvoice.customer_name}.` : ''}
        confirmLabel="Delete invoice"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setPendingDeleteInvoice(null)}
      />

      {sendModalInvoice && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => setSendModalInvoice(null)}>
          <div className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-text">Send invoice to {sendModalInvoice.customer_name}</h3>
              <button onClick={() => setSendModalInvoice(null)} className="text-slate-dim hover:text-slate-text"><X size={18} /></button>
            </div>
            <div className="space-y-1">
              <button onClick={() => handleSendEmail(sendModalInvoice)} className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-navy-700/50 transition-colors text-left">
                <div className="w-9 h-9 rounded-full bg-blue-50 dark:bg-blue-500/15 flex items-center justify-center flex-shrink-0 text-blue-500">
                  <Mail size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-slate-text">Email</p>
                  <p className="text-xs text-slate-dim truncate">{sendModalInvoice.customer_email || 'No email on file - you\'ll be asked for one'}</p>
                </div>
              </button>
              <button onClick={() => handleSendWhatsApp(sendModalInvoice)} className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-navy-700/50 transition-colors text-left">
                <div className="w-9 h-9 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0 text-brand-500">
                  <MessageCircle size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-slate-text">WhatsApp</p>
                  <p className="text-xs text-slate-dim truncate">{sendModalInvoice.customer_phone ? 'Opens WhatsApp with the message ready to send' : 'No phone number on file'}</p>
                </div>
              </button>
              <button onClick={() => handleSendSMS(sendModalInvoice)} className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-navy-700/50 transition-colors text-left">
                <div className="w-9 h-9 rounded-full bg-amber-50 dark:bg-amber-500/15 flex items-center justify-center flex-shrink-0 text-amber-500">
                  <Send size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-slate-text">Text message</p>
                  <p className="text-xs text-slate-dim truncate">{sendModalInvoice.customer_phone ? 'Opens your messaging app' : 'No phone number on file'}</p>
                </div>
              </button>
              {typeof navigator !== 'undefined' && navigator.share && (
                <button onClick={() => handleNativeShare(sendModalInvoice)} className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-navy-700/50 transition-colors text-left">
                  <div className="w-9 h-9 rounded-full bg-navy-700 flex items-center justify-center flex-shrink-0 text-slate-text">
                    <Share2 size={16} />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm text-slate-text">More options...</p>
                    <p className="text-xs text-slate-dim truncate">Share via any app on this device</p>
                  </div>
                </button>
              )}
              <button onClick={() => handleCopyText(sendModalInvoice)} className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-navy-700/50 transition-colors text-left">
                <div className="w-9 h-9 rounded-full bg-navy-700 flex items-center justify-center flex-shrink-0 text-slate-text">
                  <Copy size={16} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-slate-text">Copy details</p>
                  <p className="text-xs text-slate-dim truncate">Paste it anywhere yourself</p>
                </div>
              </button>
            </div>
          </div>
        </div>
      )}

      {emailPromptInvoice && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={() => setEmailPromptInvoice(null)}>
          <div className="card w-full sm:max-w-sm p-5 rounded-b-none sm:rounded-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-semibold text-slate-text mb-1">No email on file</h3>
            <p className="text-xs text-slate-dim mb-4">Enter an email address to send this invoice to.</p>
            <input
              type="email"
              autoFocus
              className="input mb-4"
              placeholder="customer@example.com"
              value={emailInput}
              onChange={e => setEmailInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleConfirmEmailPrompt()}
            />
            <div className="flex gap-3">
              <button onClick={() => setEmailPromptInvoice(null)} className="btn-ghost flex-1">Cancel</button>
              <button onClick={handleConfirmEmailPrompt} disabled={!emailInput.trim()} className="btn-primary flex-1">Send</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )

  // --- List view ---
  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Invoices</h1>
        <button onClick={openNew} className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center hover:bg-brand-600 transition-colors flex-shrink-0">
          <Plus size={18} />
        </button>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {['', 'DRAFT', 'SENT', 'PAID'].map(s => (
          <button key={s} onClick={() => setStatusFilter(s)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${statusFilter === s ? 'border-brand-500 text-brand-500 bg-brand-50 dark:bg-brand-500/10' : 'border-navy-600 text-slate-muted hover:border-navy-500'}`}>
            {s || 'All'}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{[1,2,3].map(i => <div key={i} className="card h-16 animate-pulse" />)}</div>
      ) : invoices.length === 0 ? (
        <div className="card p-10 text-center">
          <FileText size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">No invoices yet.</p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {invoices.map(inv => {
            const meta = STATUS_META[inv.status]
            return (
              <button key={inv.id} onClick={async () => {
                const { data } = await api.get(`/stores/${activeStore.id}/invoices/${inv.id}/`)
                setSelected(data.invoice)
                setView('detail')
              }} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/30 transition-colors text-left">
                <div className="w-9 h-9 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center text-brand-600 dark:text-brand-400 font-bold text-sm flex-shrink-0">
                  {inv.customer_name?.[0]?.toUpperCase() || <User size={14} />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-text truncate">{inv.customer_name}</p>
                  <p className="text-xs text-slate-dim mt-0.5">{formatDate(inv.created_at)}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="font-mono text-sm text-slate-text">{formatCurrency(inv.total_amount)}</p>
                  <span className={`badge ${meta?.badge} mt-1 inline-block`}>{meta?.label}</span>
                </div>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
