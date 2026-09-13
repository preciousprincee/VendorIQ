import { Lock } from 'lucide-react'
import { useSubscription } from '../../context/SubscriptionContext'
import { FEATURE_COPY } from '../../lib/planFeatures'

/**
 * The inline "Unlock X" card from the spec:
 *   "Unlock Advanced Analytics"
 *   "See which products are driving your profit..."
 *   [Upgrade to Pro]
 *
 * Used directly, or via <FeatureGate> as the default fallback for a locked
 * feature. `compact` renders a smaller version for use inside a dashboard
 * grid card rather than as a full-width panel.
 */
export default function UpgradePrompt({ feature, title, description, compact = false }) {
  const { openUpgradeModal } = useSubscription()
  const copy = FEATURE_COPY[feature] || {}
  const resolvedTitle = title || copy.title || 'Upgrade to Pro'
  const resolvedDescription = description || copy.description || 'This feature is available on the Pro plan.'

  const handleClick = () => openUpgradeModal({ feature, title: resolvedTitle, description: resolvedDescription })

  if (compact) {
    return (
      <button onClick={handleClick} className="card p-4 text-left w-full hover:border-brand-500/40 transition-colors">
        <div className="flex items-center gap-2 mb-1.5">
          <Lock size={13} className="text-slate-dim flex-shrink-0" />
          <p className="text-sm font-medium text-slate-text truncate">{resolvedTitle.replace(/^Unlock /, '')}</p>
        </div>
        <span className="badge bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400">Pro feature</span>
      </button>
    )
  }

  return (
    <div className="card p-6 text-center">
      <div className="w-10 h-10 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center mx-auto mb-3">
        <Lock size={18} className="text-brand-500" />
      </div>
      <p className="text-sm font-semibold text-slate-text mb-1">{resolvedTitle}</p>
      <p className="text-xs text-slate-dim mb-4 max-w-xs mx-auto leading-relaxed">{resolvedDescription}</p>
      <button onClick={handleClick} className="btn-primary text-sm px-5 py-2.5">Upgrade to Pro</button>
    </div>
  )
}
