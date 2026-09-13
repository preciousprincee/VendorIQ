import { useCallback } from 'react'
import { useSubscription } from '../context/SubscriptionContext'
import { FEATURE_COPY } from '../lib/planFeatures'

/**
 * useFeatureAccess('ai_assistant') -> { allowed, requireAccess }
 *
 * `allowed` is for rendering (show/hide, disable a button, badge a nav
 * item). `requireAccess()` is for gating an ACTION (a click handler) - it
 * returns true/false and, when false, opens the upgrade modal with copy
 * for that specific feature so the person sees why it's worth paying for
 * instead of just a disabled button. Use requireAccess to guard entry into
 * a flow (e.g. opening the "new invoice" form); the backend is still the
 * real enforcement point (see apps/billing/entitlements.py) - this only
 * saves a round-trip and gives nicer, feature-specific copy than the
 * generic 402 fallback.
 */
export function useFeatureAccess(featureKey) {
  const { hasFeature, openUpgradeModal } = useSubscription()
  const allowed = hasFeature(featureKey)

  const requireAccess = useCallback(() => {
    if (allowed) return true
    const copy = FEATURE_COPY[featureKey] || {}
    openUpgradeModal({
      feature: featureKey,
      title: copy.title || 'Upgrade to Pro',
      description: copy.description || 'This is a Pro feature.',
    })
    return false
  }, [allowed, featureKey, openUpgradeModal])

  return { allowed, requireAccess }
}
