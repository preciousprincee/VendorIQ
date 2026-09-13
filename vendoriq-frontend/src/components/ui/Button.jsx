import { cn } from '../../lib/utils'

const variants = {
  primary: 'bg-[#F5A623] text-[#0F1B2D] font-semibold hover:bg-[#FDC95F] active:scale-95',
  ghost: 'text-[#8896A5] hover:text-white hover:bg-white/5',
  danger: 'bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20',
  outline: 'border border-white/10 text-white hover:bg-white/5',
}

export default function Button({ variant = 'primary', className, children, loading, ...props }) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        className
      )}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? (
        <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
      ) : null}
      {children}
    </button>
  )
}
