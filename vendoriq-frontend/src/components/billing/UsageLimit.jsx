import { useSubscription } from '../../context/SubscriptionContext'

/**
 * <UsageLimit label="Products" used={72} limit={100} />
 *
 * Renders nothing when `limit` is null (unlimited - i.e. already on Pro,
 * or a plan with no cap on this resource), so pages can render this
 * unconditionally without an isPro check first. Turns amber near the cap
 * and red at/over it, with an upgrade link that appears once the limit is
 * actually reached.
 */
export default function UsageLimit({ label, used, limit, unit }) {
  const { openUpgradeModal } = useSubscription()
  if (limit == null) return null

  const pct = Math.min(100, Math.round((used / limit) * 100))
  const atLimit = used >= limit
  const near = pct >= 80

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-slate-muted">{label}</p>
        <p className="text-xs font-mono text-slate-dim">{used}/{limit}{unit ? ` ${unit}` : ''}</p>
      </div>
      <div className="h-1.5 rounded-full bg-navy-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${atLimit ? 'bg-red-500' : near ? 'bg-amber-500' : 'bg-brand-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {atLimit && (
        <button
          onClick={() => openUpgradeModal({
            title: `You've reached the ${limit}${unit ? ` ${unit}` : ''} limit on the Free plan.`,
            description: `Upgrade to Pro for unlimited ${label.toLowerCase()}.`,
          })}
          className="text-xs text-brand-500 font-medium mt-2"
        >
          Upgrade to Pro &rarr;
        </button>
      )}
    </div>
  )
}
