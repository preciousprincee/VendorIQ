import { useState, useEffect, useRef } from 'react'
import { X, Check, Lock, Sparkles } from 'lucide-react'
import api from '../../lib/api'
import { formatCurrency, getErrorMessage } from '../../lib/utils'
import { useAuth } from '../../context/AuthContext'
import toast from 'react-hot-toast'
import { track } from '../../lib/analytics'

// The API answers 403 {code: 'verification_required'} until BOTH the email
// and the phone number are verified. Send the person to do that instead of
// just flashing an error. (Full page navigation: this modal can be mounted
// outside the router tree.)
function sendToVerificationIfNeeded(err) {
  if (err?.response?.data?.code === 'verification_required') {
    toast.error(err.response.data.error || 'Please verify your account first.')
    window.location.assign('/verify')
    return true
  }
  return false
}

/**
 * The single upgrade experience for the whole app - opened either by a
 * direct "Upgrade to Pro" click (SubscriptionContext.openUpgradeModal) or
 * automatically whenever the backend returns a 402 upgrade-required
 * response (see the 'viq:upgrade-required' listener in
 * SubscriptionContext, fed by the interceptor in lib/api.js).
 *
 * Pro is sold in three billing cycles (Monthly / 6-Month / Annual - see
 * apps/billing/plans.py), so this modal lets the person pick one before
 * paying; `subscription.pricing` (from GET /api/billing/subscription/)
 * carries the live price + monthly-equivalent for each, never hardcoded
 * here.
 *
 * Upgrade flow: this always tries a REAL Paystack test-mode payment first
 * (initialize on the backend for the chosen billing_cycle, open Paystack's
 * inline popup using the public key the backend hands back, verify on the
 * backend once it reports success - see
 * apps/billing/views.py::PaystackInitializeView/PaystackVerifyView). It
 * NEVER silently grants Pro for free - the old no-payment mock flow (POST
 * /api/billing/upgrade/) only ever runs when the backend's 503 response
 * explicitly sets mockUpgradeAvailable: true, which only happens in local
 * dev (ALLOW_MOCK_UPGRADE=true AND no real Paystack keys configured - see
 * apps/billing/views.py). On any real deployment that flag is always
 * false, so a misconfigured/down Paystack shows a real "payments
 * unavailable" error instead of quietly upgrading the account. The only
 * thing checked client-side is whether Paystack's own script (loaded in
 * index.html) actually loaded - see handleUpgrade below.
 */
export default function UpgradeModal({ open, context, subscription, viewerIsOwner = true, onClose, onUpgraded }) {
  const { user } = useAuth()
  const [upgrading, setUpgrading] = useState(false)
  const [startingTrial, setStartingTrial] = useState(false)
  const [selectedCycle, setSelectedCycle] = useState(null)
  const closeRef = useRef(null)

  const pricing = subscription?.pricing || []

  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKeyDown = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  // Default to the "Most Popular" (6-Month) cycle whenever the modal opens
  // with fresh pricing data, rather than leaving nothing selected.
  useEffect(() => {
    if (!open || !pricing.length) return
    setSelectedCycle((current) => {
      if (current && pricing.some((c) => c.billingCycle === current)) return current
      return (pricing.find((c) => c.mostPopular) || pricing[0]).billingCycle
    })
  }, [open, pricing])

  if (!open) return null

  const proPlan = subscription?.plans?.find(p => p.code === 'PRO')
  const freePlan = subscription?.plans?.find(p => p.code === 'FREE')
  const activeCycle = pricing.find(c => c.billingCycle === selectedCycle) || pricing[0]
  const trialPeriodDays = subscription?.trialPeriodDays
  const showTrialCta = viewerIsOwner && subscription?.plan === 'FREE' && !subscription?.hasUsedTrial && trialPeriodDays

  const finishUpgrade = async () => {
    toast.success("You're on Pro now \u2014 every feature is unlocked.")
    await onUpgraded?.()
    onClose()
  }

  const handleMockUpgrade = async () => {
    if (!activeCycle) return
    setUpgrading(true)
    try {
      await api.post('/billing/upgrade/', { billing_cycle: activeCycle.billingCycle })
      await finishUpgrade()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setUpgrading(false)
    }
  }

  const handlePaystackUpgrade = async () => {
    if (!activeCycle) return
    setUpgrading(true)
    try {
      const { data } = await api.post('/billing/paystack/initialize/', { billing_cycle: activeCycle.billingCycle })
      track('checkout_started', { billing_cycle: activeCycle.billingCycle, source: context?.feature || 'direct' })
      const handler = window.PaystackPop.setup({
        // The public key always comes from the backend's response, which
        // reads settings.PAYSTACK_PUBLIC_KEY server-side - never a
        // frontend-only copy of it, so there's nothing to keep in sync
        // between the two deployments.
        key: data.publicKey,
        email: user?.email,
        amount: data.amountKobo,
        currency: 'NGN',
        ref: data.reference,
        onClose: () => setUpgrading(false),
        callback: (response) => {
          // Paystack's popup already ran the charge - this just confirms
          // it with our own backend (never trust the popup's word alone)
          // before actually flipping the subscription to Pro.
          api.post('/billing/paystack/verify/', { reference: response.reference })
            .then(() => finishUpgrade())   // the purchase itself is recorded by the server (subscription_purchased)
            .catch((err) => toast.error(getErrorMessage(err)))
            .finally(() => setUpgrading(false))
        },
      })
      handler.openIframe()
    } catch (err) {
      // IMPORTANT: this must NEVER silently fall back to the free
      // no-payment demo flow just because initialize failed - that was
      // the actual bug behind "I was able to upgrade without anything to
      // pay". The backend only ever offers the demo flow when it says so
      // explicitly via mockUpgradeAvailable (true only in local dev, with
      // ALLOW_MOCK_UPGRADE=true AND no real Paystack keys configured -
      // see apps/billing/views.py::PaystackInitializeView). Every other
      // failure - Paystack down, keys half-configured, a network error -
      // must show a real error and charge nothing.
      if (err?.response?.status === 503 && err.response.data?.mockUpgradeAvailable) {
        await handleMockUpgrade()
        return
      }
      if (!sendToVerificationIfNeeded(err)) toast.error(getErrorMessage(err))
      setUpgrading(false)
    }
  }

  // Try the real Paystack flow whenever its script actually loaded (it's
  // included unconditionally in index.html); only skip straight to the
  // no-payment demo if the script itself failed to load (e.g. blocked by
  // an ad blocker or a network issue) - a mere missing/misconfigured key
  // is instead caught INSIDE handlePaystackUpgrade (see its 503 handling
  // above), since only the backend actually knows whether Paystack is
  // configured.
  const handleUpgrade = (typeof window !== 'undefined' && window.PaystackPop) ? handlePaystackUpgrade : handleMockUpgrade

  const handleStartTrial = async () => {
    setStartingTrial(true)
    try {
      await api.post('/billing/trial/start/')
      toast.success(`Your ${trialPeriodDays}-day free trial has started \u2014 every Pro feature is unlocked.`)
      await onUpgraded?.()
      onClose()
    } catch (err) {
      if (!sendToVerificationIfNeeded(err)) toast.error(getErrorMessage(err))
    } finally {
      setStartingTrial(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 animate-fade-in" onClick={onClose}>
      <div
        role="dialog" aria-modal="true" aria-labelledby="upgrade-modal-title"
        className="card w-full sm:max-w-md max-h-[92vh] overflow-y-auto rounded-b-none sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-navy-700 sticky top-0 bg-navy-800 z-10">
          <p id="upgrade-modal-title" className="text-base font-bold text-slate-text">Upgrade to Pro</p>
          <button ref={closeRef} onClick={onClose} aria-label="Close" className="text-slate-muted hover:text-slate-text p-1">
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

          {pricing.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {pricing.map((cycle) => {
                const isSelected = cycle.billingCycle === selectedCycle
                const badge = cycle.mostPopular ? 'Most Popular' : cycle.bestValue ? 'Best Value' : null
                return (
                  <button
                    key={cycle.billingCycle}
                    type="button"
                    onClick={() => setSelectedCycle(cycle.billingCycle)}
                    className={`relative flex flex-col items-center rounded-xl border px-2 py-3 text-center transition-colors ${
                      isSelected ? 'border-brand-500 bg-brand-500/10' : 'border-navy-700 hover:border-navy-600'
                    }`}
                  >
                    {badge && (
                      <span className="absolute -top-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-brand-500 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-white">
                        {badge}
                      </span>
                    )}
                    <p className="mt-1 text-[11px] font-semibold text-slate-text">{cycle.label}</p>
                    <p className="mt-1 text-sm font-bold font-mono text-slate-text">{formatCurrency(cycle.priceNgn)}</p>
                    <p className="text-[10px] text-slate-dim">{formatCurrency(cycle.monthlyEquivalentNgn)}/mo</p>
                  </button>
                )
              })}
            </div>
          )}

          {proPlan?.tagline && <p className="text-xs text-slate-dim">{proPlan.tagline}</p>}

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
                <p className="text-[11px] text-slate-dim text-center leading-relaxed">
                  By upgrading you agree to our{' '}
                  <a href="/legal/terms" target="_blank" rel="noopener noreferrer" className="text-brand-500 hover:underline">Terms</a>
                  {' '}and{' '}
                  <a href="/legal/refunds" target="_blank" rel="noopener noreferrer" className="text-brand-500 hover:underline">Refund Policy</a>.
                </p>
                <button onClick={handleUpgrade} disabled={upgrading || !activeCycle} className="btn-primary w-full">
                  {upgrading ? 'Upgrading\u2026' : activeCycle ? `Upgrade to Pro \u2014 ${formatCurrency(activeCycle.priceNgn)} (${activeCycle.label})` : 'Upgrade to Pro'}
                </button>
                {showTrialCta && (
                  <button onClick={handleStartTrial} disabled={startingTrial} className="btn-ghost w-full flex items-center justify-center gap-1.5">
                    <Sparkles size={14} />
                    {startingTrial ? 'Starting\u2026' : `Or try Pro free for ${trialPeriodDays} days`}
                  </button>
                )}
                <p className="text-[11px] text-slate-dim text-center">
                  You'll be taken to Paystack's secure checkout to pay. In test mode, use Paystack's test card
                  (4084 0840 8408 4081, any future date/CVV) to simulate a successful payment.
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
