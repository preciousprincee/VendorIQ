import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Printer, MessageCircle, X, WifiOff, AlertTriangle } from 'lucide-react'
import { methodLabel } from '../../lib/offline/money'
import { receiptToText } from '../../lib/offline/receipt'
import { formatDateTime } from '../../lib/utils'

const money = (n) => `\u20a6${Number(n).toLocaleString('en-NG', { minimumFractionDigits: Number.isInteger(Number(n)) ? 0 : 2, maximumFractionDigits: 2 })}`

function Row({ label, value, bold = false }) {
  return (
    <div className={`flex justify-between gap-3 ${bold ? 'font-bold text-base' : ''}`}>
      <span>{label}</span><span className="font-mono">{value}</span>
    </div>
  )
}

/**
 * The receipt, on screen and on paper. Built only from the receipt object, so
 * it works with no connection at all (the till prints before the server has
 * even seen the sale). `syncStatus` is shown on screen only, never printed.
 *   actions: extra buttons, e.g. [{label, onClick}] ("New sale")
 */
export default function ReceiptModal({ receipt, onClose, syncStatus = 'synced', syncError = '', customerPhone = '', primary }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const shareWhatsApp = () => {
    const digits = String(customerPhone || '').replace(/\D/g, '')
    const to = digits ? (digits.startsWith('0') ? `234${digits.slice(1)}` : digits) : ''
    window.open(`https://wa.me/${to}?text=${encodeURIComponent(receiptToText(receipt))}`, '_blank', 'noopener,noreferrer')
  }

  return createPortal(
    <div className="receipt-portal fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/50 p-0 sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Receipt"
        className="card w-full sm:max-w-sm max-h-[92vh] flex flex-col rounded-b-none sm:rounded-2xl animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <div className="no-print flex items-center justify-between px-4 pt-3">
          <p className="text-sm font-semibold text-slate-text">Receipt</p>
          <button onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text"><X size={18} /></button>
        </div>

        {syncStatus === 'pending' && (
          <p className="no-print mx-4 mt-2 flex items-start gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <WifiOff size={14} className="mt-0.5 flex-shrink-0" />Saved on this device - it will sync automatically when you're back online.
          </p>
        )}
        {syncStatus === 'failed' && (
          <p className="no-print mx-4 mt-2 flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-300">
            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />{syncError || 'The server did not accept this sale.'}
          </p>
        )}

        <div className="receipt-scroll overflow-y-auto p-4">
          <div className="receipt-paper text-slate-text text-[13px] leading-snug">
            <div className="text-center mb-3">
              <p className="font-bold text-base">{receipt.storeName}</p>
              {receipt.storeLocation && <p className="text-xs">{receipt.storeLocation}</p>}
              <p className="text-xs mt-1">Receipt #{receipt.receiptNo}</p>
              <p className="text-xs">{formatDateTime(receipt.createdAt)}</p>
              {receipt.cashier && <p className="text-xs">Served by {receipt.cashier}</p>}
              {receipt.customerName && <p className="text-xs">Customer: {receipt.customerName}</p>}
            </div>

            <div className="border-t border-dashed border-slate-dim/50 py-2 space-y-1.5">
              {receipt.items.map((i, idx) => (
                <div key={idx}>
                  <div className="flex justify-between gap-3">
                    <span className="min-w-0 break-words">{i.name}</span>
                    <span className="font-mono flex-shrink-0">{money(i.lineTotal)}</span>
                  </div>
                  <p className="text-xs opacity-70">{i.quantity} x {money(i.unitPrice)}{i.returned > 0 ? ` (${i.returned} returned)` : ''}</p>
                </div>
              ))}
            </div>

            <div className="border-t border-dashed border-slate-dim/50 py-2 space-y-1">
              {receipt.discount > 0 && <Row label="Subtotal" value={money(receipt.subtotal)} />}
              {receipt.discount > 0 && <Row label="Discount" value={`-${money(receipt.discount)}`} />}
              <Row label="TOTAL" value={money(receipt.total)} bold />
              {receipt.returned > 0 && <Row label="Returned" value={`-${money(receipt.returned)}`} />}
              {receipt.returned > 0 && <Row label="Net total" value={money(receipt.netTotal)} bold />}
            </div>

            <div className="border-t border-dashed border-slate-dim/50 py-2 space-y-1">
              {receipt.payments.map((p, idx) => <Row key={idx} label={methodLabel(p.method)} value={money(p.amount)} />)}
              {receipt.change > 0 && <Row label="Change" value={money(receipt.change)} />}
              {receipt.balanceDue > 0 && <Row label="BALANCE OWING" value={money(receipt.balanceDue)} bold />}
            </div>

            {receipt.note && <p className="text-xs text-center mt-1">{receipt.note}</p>}
            <p className="text-center text-xs mt-3">Thank you for your patronage!</p>
          </div>
        </div>

        <div className="no-print flex gap-2 p-3 border-t border-navy-700">
          <button onClick={() => window.print()} className="btn-ghost flex-1 flex items-center justify-center gap-1.5 text-xs">
            <Printer size={14} />Print
          </button>
          <button onClick={shareWhatsApp} className="btn-ghost flex-1 flex items-center justify-center gap-1.5 text-xs">
            <MessageCircle size={14} />WhatsApp
          </button>
          {primary ? (
            <button onClick={primary.onClick} className="btn-primary flex-1 text-xs">{primary.label}</button>
          ) : (
            <button onClick={onClose} className="btn-primary flex-1 text-xs">Done</button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}
