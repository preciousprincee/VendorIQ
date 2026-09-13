import { cn } from '../../lib/utils'

export default function Input({ label, error, className, ...props }) {
  return (
    <div className="w-full">
      {label && <label className="block text-xs font-medium text-[#8896A5] uppercase tracking-wider mb-1.5">{label}</label>}
      <input
        className={cn(
          'w-full bg-[#070E1A] border rounded-xl px-4 py-3 text-white placeholder-[#8896A5] focus:outline-none transition-all duration-150 text-sm',
          error ? 'border-red-500/50 focus:border-red-500' : 'border-white/10 focus:border-[#F5A623]/60 focus:ring-1 focus:ring-[#F5A623]/30',
          className
        )}
        {...props}
      />
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}
