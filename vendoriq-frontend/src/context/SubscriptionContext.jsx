import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../lib/api'
import { useAuth } from './AuthContext'
import { useStore } from './StoreContext'
import UpgradeModal from '../components/billing/UpgradeModal'
import { track } from '../lib/analytics'

const SubscriptionContext = createContext(null)

/**
 * Single source of truth on the frontend for "what plan is this account
 * on, and what does it unlock" - backed by GET /api/billing/subscription/
 * (apps/billing/views.py::SubscriptionView), which is itself backed by the
 * Subscription model, NOT anything computed client-side. This context just
 * caches that response and exposes convenience helpers; it never decides
 * access on its own authority - the backend re-checks everything (see
 * apps/billing/entitlements.py), so a stale or tampered client value here
 * can make the UI wrong for a moment but can never actually bypass a limit.
 *
 * IMPORTANT: a Subscription belongs to a *user*, but what actually governs
 * a store's limits/features is the STORE OWNER's plan, not whoever's
 * logged in - a staff member's own personal subscription is always Free
 * (they never subscribe themselves). So this always asks the backend for
 * the ACTIVE STORE's subscription (?store_id=...), not just "my"
 * subscription - see _resolve_billing_subject in the backend view. That's
 * what makes a staff account correctly show Pro when the owner is Pro, and
 * correctly drop back to Free the moment the owner's Pro subscription
 * actually expires - both were broken before this refetched on `user`
 * alone and never told the backend which store's owner to look up.
 *
 * Also hosts the single global <UpgradeModal/> - both explicit "Upgrade to
 * Pro" button clicks (via openUpgradeModal) and automatic 402 responses
 * from any API call (via the 'viq:upgrade-required' window event dispatched
 * in lib/api.js) open the same modal instance, so there's only ever one
 * upgrade experience in the app, not a different one per page.
 */
export function SubscriptionProvider({ children }) {
  const { user } = useAuth()
  const { activeStore } = useStore()
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading] = useState(false)
  const [modalContext, setModalContext] = useState(null) // null = closed, else {title, description, feature, ...}

  const refresh = useCallback(async () => {
    if (!user) { setSubscription(null); return }
    setLoading(true)
    try {
      const { data } = await api.get('/billing/subscription/', {
        params: activeStore ? { store_id: activeStore.id } : undefined,
      })
      setSubscription(data)
    } catch (err) {
      // Non-critical to the rest of the app - it still works with
      // subscription===null; feature checks fail closed (see
      // useFeatureAccess) rather than open. But silently swallowing this
      // means a real backend problem (e.g. a migration that hasn't been
      // run yet) looks identical to "everything's just on the Free plan,
      // nothing to see" - no trial offer, no Pro badge, no error, nothing
      // to go on. Logging it means it's at least visible in devtools
      // instead of a total dead end.
      console.error('Failed to load subscription:', err)
    } finally {
      setLoading(false)
    }
  }, [user, activeStore?.id])

  // Re-fetch whenever the active store changes (switching stores can mean
  // switching to a store with a different owner/plan), not just on login.
  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    const handler = (e) => {
      const detail = e.detail || {}
      // The server refused a Pro-only action (402): that is a feature-gate hit.
      if (detail.feature) track('feature_gate_hit', { feature: detail.feature, source: 'api' })
      setModalContext(detail)
    }
    window.addEventListener('viq:upgrade-required', handler)
    return () => window.removeEventListener('viq:upgrade-required', handler)
  }, [])

  const openUpgradeModal = useCallback((context = {}) => {
    // Only a locked FEATURE counts as a gate hit - a plain "Upgrade" button click carries no feature.
    if (context?.feature) track('feature_gate_hit', { feature: context.feature, source: 'ui' })
    setModalContext(context)
  }, [])
  const closeUpgradeModal = useCallback(() => setModalContext(null), [])

  const plan = subscription?.plan || 'FREE'
  const isPro = plan === 'PRO'
  const hasFeature = useCallback(
    (featureKey) => !!subscription?.planConfig?.features?.[featureKey],
    [subscription]
  )

  const value = {
    subscription,
    loading,
    refresh,
    plan,
    isPro,
    status: subscription?.status,
    cancelAtPeriodEnd: subscription?.cancelAtPeriodEnd,
    currentPeriodEnd: subscription?.currentPeriodEnd,
    usage: subscription?.usage,
    limits: subscription?.planConfig?.limits,
    plansCatalog: subscription?.plans,
    // The live Monthly / 6-Month / Annual price catalog (see
    // apps/billing/models.py::get_plan_pricing_catalog) - always present,
    // even on Free, so the pricing/upgrade UI never has to guess prices.
    pricing: subscription?.pricing ?? [],
    billingCycle: subscription?.billingCycle ?? null,
    amountPaidNgn: subscription?.amountPaidNgn ?? 0,
    // Trial state - isTrialActive drives the "N days left in your trial"
    // banner; hasUsedTrial/trialPeriodDays drive whether and how a
    // "start your free trial" CTA is offered to a Free account (see
    // SubscriptionPage and UpgradeModal). trialPeriodDays is always
    // present, even before anyone has started a trial, so the CTA can say
    // "Start your 14-day trial" without a trial existing yet.
    isTrialActive: subscription?.isTrialActive ?? false,
    trialDaysRemaining: subscription?.trialDaysRemaining ?? 0,
    hasUsedTrial: subscription?.hasUsedTrial ?? false,
    trialPeriodDays: subscription?.trialPeriodDays,
    // False for a staff member looking at their (Pro or Free) store's
    // plan - they can see it, but only the owner can upgrade/cancel it.
    viewerIsOwner: subscription?.viewerIsOwner ?? true,
    hasFeature,
    openUpgradeModal,
    closeUpgradeModal,
  }

  return (
    <SubscriptionContext.Provider value={value}>
      {children}
      <UpgradeModal
        open={modalContext !== null}
        context={modalContext}
        subscription={subscription}
        viewerIsOwner={value.viewerIsOwner}
        onClose={closeUpgradeModal}
        onUpgraded={refresh}
      />
    </SubscriptionContext.Provider>
  )
}

export const useSubscription = () => {
  const ctx = useContext(SubscriptionContext)
  if (!ctx) throw new Error('useSubscription must be used within SubscriptionProvider')
  return ctx
}
