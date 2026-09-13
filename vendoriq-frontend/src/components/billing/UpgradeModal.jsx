import { useState } from 'react'
import { X, Check, Lock, Sparkles } from 'lucide-react'
import api from '../../lib/api'
import { formatCurrency, getErrorMessage } from '../../lib/utils'
import toast from 'react-hot-toast'

/**
 * The single upgrade experience for the whole app - opened either by a
 * direct "Upgrade to Pro" click (SubscriptionContext.openUpgradeModal) or
 * automatically whenever the backend returns a 402 upgrade-required
 * response (see the 'viq:upgrade-required' listener in
 * SubscriptionContext, fed by the interceptor in lib/api.js).
 *
 * `context` carries what triggered it (a specific feature or limit) so the
 * top banner can explain exactly what the person was trying to do, above
 * the general Free vs Pro comparison.
 *
 * Upgrade flow is currently mocked (POST /api/billing/upgrade/ activates
 * Pro immediately - see apps/billing/views.py::UpgradeView) since no
 * payment gateway is wired up yet. Swapping in Paystack/Flutterwave later
 * means replacing the body of `handleUpgrade` with a redirect to that
 * provider's checkout - everything else here (the comparison UI, the
 * `onUpgraded` refresh callback) stays the same.
 */
export default function UpgradeModal({ open, context, subscription, viewerIsOwner = true, onClose, onUpgraded }) {
  const [upgrading, setUpgrading] = useState(false)
  const [startingTrial, setStartingTrial] = useState(false)
  if (!open) return null

  const proPlan = subscription?.plans?.find(p => p.code === 'PRO')
  const freePlan = subscription?.plans?.find(p => p.code === 'FREE')
  const proPrice = proPlan?.priceNgn ?? 5000
  const trialPeriodDays = subscription?.trialPeriodDays
  const showTrialCta = viewerIsOwner && subscription?.plan === 'FREE' && !subscription?.hasUsedTrial && trialPeriodDays

  const handleUpgrade = async () => {
    setUpgrading(true)
    try {
      await api.post('/billing/upgrade/')
      toast.success("You're on Pro now \u2014 every feature is unlocked.")
      await onUpgraded?.()
      onClose()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setUpgrading(false)
    }
  }

  const handleStartTrial = async () => {
    setStartingTrial(true)
    try {
      await api.post('/billing/trial/start/')
      toast.success(`Your ${trialPeriodDays}-day free trial has started \u2014 every Pro feature is unlocked.`)
      await onUpgraded?.()
      onClose()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setStartingTrial(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 animate-fade-in" onClick={onClose}>
      <div
        className="card w-full sm:max-w-md max-h-[92vh] overflow-y-auto rounded-b-none sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-navy-700 sticky top-0 bg-navy-800 z-10">
          <p className="text-base font-bold text-slate-text">Upgrade to Pro</p>
          <button onClick={onClose} className="text-slate-muted hover:text-slate-text p-1">
            <X size={20} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {context?.title && (
            <div className="bg-brand-50 dark:bg-brand-500/10 border border-brand-500/20 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-1">
                <Lock size={14} className="text-brand-500 flex-shrink-0" />
                <p className="text-sm font-semibold text-slate-text">{context.title}</p>
              </div>
              {context.description && <p className="text-xs text-slate-dim leading-relaxed">{context.description}</p>}
            </div>
          )}

          <div>
            <div className="flex items-baseline gap-1.5">
              <p className="text-3xl font-bold text-slate-text font-mono tabular-nums">{formatCurrency(proPrice)}</p>
              <p className="text-sm text-slate-dim">/month</p>
            </div>
            {proPlan?.tagline && <p className="text-xs text-slate-dim mt-1">{proPlan.tagline}</p>}
          </div>

          <div className="space-y-2.5">
            {(proPlan?.includes || [
              'Unlimited products & stores', 'Multiple staff accounts', 'Advanced analytics & reports',
              'CSV exports & invoicing', 'AI business assistant',
            ]).map((item) => (
              <div key={item} className="flex items-start gap-2.5">
                <Check size={15} className="text-brand-500 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-slate-text">{item}</p>
              </div>
            ))}
          </div>

          {freePlan && (
            <div className="bg-navy-950 rounded-xl p-3 border border-navy-700">
              <p className="text-xs font-medium text-slate-muted mb-1">You're currently on Free</p>
              <p className="text-xs text-slate-dim leading-relaxed">
                {freePlan.limits.maxStores} store &middot; {freePlan.limits.maxProductsPerStore} products &middot; {freePlan.limits.maxUsersPerStore} user
              </p>
            </div>
          )}

          <div className="space-y-2">
            {viewerIsOwner ? (
              <>
                <button onClick={handleUpgrade} disabled={upgrading} className="btn-primary w-full">
                  {upgrading ? 'Upgrading\u2026' : `Upgrade to Pro \u2014 ${formatCurrency(proPrice)}/month`}
                </button>
                {showTrialCta && (
                  <button onClick={handleStartTrial} disabled={startingTrial} className="btn-ghost w-full flex items-center justify-center gap-1.5">
                    <Sparkles size={14} />
                    {startingTrial ? 'Starting\u2026' : `Or try Pro free for ${trialPeriodDays} days`}
                  </button>
                )}
                <p className="text-[11px] text-slate-dim text-center">
                  Demo upgrade — no payment is collected. A real payment provider can be connected here later.
                </p>
              </>
            ) : (
              // Staff (managers/cashiers) can see what Pro unlocks but only
              // the store OWNER's account can actually pay for it - showing
              // an "Upgrade" button here would upgrade the staff member's
              // own unrelated personal account and do nothing for the
              // store, which is confusing at best. Point them at the owner
              // instead of letting them click a dead end.
              <div className="bg-navy-950 rounded-xl p-3.5 border border-navy-700 text-center">
                <p className="text-xs text-slate-text font-medium mb-0.5">Ask your store owner to upgrade</p>
                <p className="text-[11px] text-slate-dim">Only the store owner's account can upgrade to Pro.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
