import { clsx } from '../../lib/utils'

export const Spinner = ({ size = 'md', className = '' }) => {
  const s = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }[size]
  return (
    <svg className={`animate-spin text-emerald-500 ${s} ${className}`} fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

export const EmptyState = ({ icon: Icon, title, description, action }) => (
  <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
    {Icon && (
      <div className="w-14 h-14 rounded-2xl bg-navy-800 border border-navy-700 flex items-center justify-center mb-4">
        <Icon className="w-6 h-6 text-slate-400" />
      </div>
    )}
    <p className="font-display font-semibold text-slate-200 mb-1">{title}</p>
    {description && <p className="text-sm text-slate-400 mb-4 max-w-xs">{description}</p>}
    {action}
  </div>
)

export const StatCard = ({ label, value, sub, accent = false, className = '' }) => (
  <div className={clsx('card p-4', accent && 'border-l-2 border-l-emerald-500', className)}>
    <p className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-1">{label}</p>
    <p className="stat-number profit-pulse">{value}</p>
    {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
  </div>
)

export const Badge = ({ children, variant = 'slate' }) => {
  const variants = {
    green: 'badge-green',
    amber: 'badge-amber',
    red: 'badge-red',
    slate: 'badge-slate',
  }
  return <span className={variants[variant]}>{children}</span>
}

export const Modal = ({ open, onClose, title, children, maxWidth = 'max-w-md' }) => {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="absolute inset-0 bg-navy-950/80 backdrop-blur-sm" onClick={onClose} />
      <div className={clsx(
        'relative bg-navy-800 border border-navy-700 w-full rounded-t-2xl sm:rounded-2xl',
        'max-h-[92vh] overflow-y-auto animate-slide-up',
        maxWidth
      )}>
        <div className="flex items-center justify-between p-5 border-b border-navy-700">
          <h2 className="font-display font-semibold text-slate-100">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 transition-colors p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export const FormField = ({ label, error, children }) => (
  <div className="mb-4">
    {label && <label className="label">{label}</label>}
    {children}
    {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
  </div>
)

export const PageHeader = ({ title, subtitle, action }) => (
  <div className="flex items-start justify-between mb-6">
    <div>
      <h1 className="font-display font-bold text-xl text-slate-100">{title}</h1>
      {subtitle && <p className="text-sm text-slate-400 mt-0.5">{subtitle}</p>}
    </div>
    {action}
  </div>
)
