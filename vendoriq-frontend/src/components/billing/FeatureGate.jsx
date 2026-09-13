import { useFeatureAccess } from '../../hooks/useFeatureAccess'
import UpgradePrompt from './UpgradePrompt'

/**
 * <FeatureGate feature="ai_assistant" title="..." description="...">
 *   <ActualProUI />
 * </FeatureGate>
 *
 * Renders children when the store owner's plan includes `feature`;
 * otherwise renders an upgrade prompt in its place (or `fallback`, if a
 * page needs custom locked-state UI instead of the default card). Never
 * silently hides a feature with nothing in its place - per the spec, a
 * locked feature should always explain itself and offer the upgrade path.
 */
export default function FeatureGate({ feature, title, description, fallback, compact, children }) {
  const { allowed } = useFeatureAccess(feature)
  if (allowed) return children
  if (fallback) return fallback
  return <UpgradePrompt feature={feature} title={title} description={description} compact={compact} />
}
