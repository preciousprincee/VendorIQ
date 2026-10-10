import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Store, Package, Users, Clock, Sparkles } from 'lucide-react'
import { useSubscription } from '../context/SubscriptionContext'
import { useStore } from '../context/StoreContext'
import api from '../lib/api'
import { formatCurrency, formatDate, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'
import ConfirmDialog from '../components/ui/ConfirmDialog'

function UsageRow({ icon: Icon, label, used, limit, unit = '' }) {
  const unlimited = limit == null
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <Icon size={16} className="text-slate-dim flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-text">{label}</p>
      </div>
      <p className="font-mono text-sm text-slate-dim flex-shrink-0">
        {unlimited ? `${used} \u00b7 Unlimited` : `${used}/${limit}${unit}`}
      </p>
    </div>
  )
}

// One of the three billing-cycle cards (Monthly / 6-Month / Annual) from
// GET /api/billing/subscription/'s `pricing` field - never a hardcoded
// price, always the live value from apps/billing/models.py::PlanPrice.
function CycleCard({ cycle, isCurrent, onUpgrade }) {
  const badge = cycle.mostPopular ? 'Most Popular' : cycle.bestValue ? 'Best Value' : null
  return (
    <div className={`card p-4 relative ${cycle.mostPopular ? 'border-brand-500/50' : ''} ${isCurrent ? 'border-brand-500' : ''}`}>
      {badge && (
        <span className="absolute -top-2.5 left-4 rounded-full bg-brand-500 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
          {badge}
        </span>
      )}
      <p className="text-xs font-bold uppercase tracking-wider text-slate-dim mt-1">{cycle.label}</p>
      <div className="flex items-baseline gap-1 mt-1 mb-0.5">
        <p className="text-xl font-bold font-mono text-slate-text">{formatCurrency(cycle.priceNgn)}</p>
        <p className="text-xs text-slate-dim">/{cycle.billingPeriodMonths === 1 ? 'month' : `${cycle.billingPeriodMonths} months`}</p>
      </div>
      {cycle.billingPeriodMonths > 1 && (
        <p className="text-xs text-slate-dim mb-3">{formatCurrency(cycle.monthlyEquivalentNgn)}/month equivalent</p>
      )}
      {cycle.billingPeriodMonths === 1 && <p className="text-xs text-slate-dim mb-3">Flexible monthly plan.</p>}
      {isCurrent ? (
        <span className="badge-success">Current plan</span>
      ) : (
        <button onClick={onUpgrade} className="btn-primary w-full text-sm">Choose {cycle.label}</button>
      )}
    </div>
  )
}

export default function SubscriptionPage() {
  const navigate = useNavigate()
  const { activeStore } = useStore()
  const {
    subscription, plan, isPro, status, cancelAtPeriodEnd, currentPeriodEnd, usage, limits, pricing, billingCycle,
    amountPaidNgn, isTrialActive, trialDaysRemaining, hasUsedTrial, trialPeriodDays, viewerIsOwner, refresh, openUpgradeModal,
  } = useSubscription()
  const [working, setWorking] = useState(false)
  const [startingTrial, setStartingTrial] = useState(false)
  const [confirmingCancel, setConfirmingCancel] = useState(false)

  if (!subscription) {
    return (
      <div className="p-5 lg:p-6 max-w-xl lg:mx-auto space-y-4">
        <div className="h-6 bg-navy-800 rounded w-40 animate-pulse" />
        <div className="h-40 bg-navy-800 rounded-2xl animate-pulse" />
      </div>
    )
  }

  const handleStartTrial = async () => {
    setStartingTrial(true)
    try {
      await api.post('/billing/trial/start/')
      toast.success(`Your ${trialPeriodDays}-day free trial has started \u2014 every Pro feature is unlocked.`)
      await refresh()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setStartingTrial(false)
    }
  }

  const handleCancel = async () => {
    setWorking(true)
    try {
      await api.post('/billing/cancel/')
      toast.success('Subscription set to cancel at period end.')
      await refresh()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setWorking(false)
      setConfirmingCancel(false)
    }
  }

  const handleResume = async () => {
    setWorking(true)
    try {
      await api.post('/billing/resume/')
      toast.success('Subscription resumed.')
      await refresh()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setWorking(false)
    }
  }

  const productUsage = activeStore ? (usage?.productsByStore?.[activeStore.id] ?? 0) : 0
  const staffUsage = activeStore ? (usage?.staffByStore?.[activeStore.id] ?? 1) : 1
  // Only a real paid Pro subscription (not a trial, not an admin comp) can
  // be "managed"/cancelled by the user - see CancelSubscriptionView on the
  // backend, which rejects both of those cases with a clearer message than
  // a generic error would give.
  const canManagePlan = isPro && (status === 'ACTIVE' || status === 'CANCELLED')
  const showTrialCta = viewerIsOwner && plan === 'FREE' && !hasUsedTrial && trialPeriodDays

  return (
    <div className="p-5 lg:p-6 max-w-xl lg:mx-auto animate-fade-in">
      <div className="flex items-center gap-2 mb-5">
        <button onClick={() => navigate('/profile')} className="text-slate-muted hover:text-slate-text">
          <ChevronLeft size={22} />
        </button>
        <h1 className="text-xl font-bold text-slate-text">Subscription &amp; Billing</h1>
      </div>

      {isTrialActive && (
        <div className="card-accent p-4 mb-5">
          <div className="flex items-center gap-1.5 mb-1">
            <Sparkles size={14} className="text-brand-500" />
            <p className="text-sm text-slate-text font-medium">
              {trialDaysRemaining} day{trialDaysRemaining === 1 ? '' : 's'} left in your free trial
            </p>
          </div>
          <p className="text-xs text-slate-dim mb-3">
            You have full Pro access until your trial ends, then you'll move back to Free. Upgrade anytime to keep everything without a gap.
          </p>
          {viewerIsOwner && (
            <button onClick={() => openUpgradeModal()} className="btn-primary text-sm px-4 py-2">
              Upgrade to Pro now
            </button>
          )}
        </div>
      )}

      {isPro && cancelAtPeriodEnd && (
        <div className="card-accent p-4 mb-5">
          <p className="text-sm text-slate-text font-medium mb-1">Your subscription is set to cancel</p>
          <p className="text-xs text-slate-dim mb-3">
            You'll keep Pro features until {currentPeriodEnd ? formatDate(currentPeriodEnd) : 'the end of your billing period'}, then move to the Free plan. Your data stays safe either way.
          </p>
          <button onClick={handleResume} disabled={working} className="btn-primary text-sm px-4 py-2">
            {working ? 'Working\u2026' : 'Resume subscription'}
          </button>
        </div>
      )}

      {isPro && !isTrialActive && (
        <div className="card p-4 mb-5 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-text">
              {formatCurrency(amountPaidNgn)} &middot; {pricing.find(c => c.billingCycle === billingCycle)?.label || billingCycle}
            </p>
            {!cancelAtPeriodEnd && currentPeriodEnd && (
              <p className="text-xs text-slate-dim mt-0.5">Renews {formatDate(currentPeriodEnd)}</p>
            )}
          </div>
          {canManagePlan && (
            <button onClick={() => setConfirmingCancel(true)} disabled={working} className="btn-ghost text-sm">
              {working ? 'Working\u2026' : 'Manage plan'}
            </button>
          )}
        </div>
      )}

      <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">
        {isPro ? 'Change plan' : 'Choose a plan'}
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        {pricing.map((cycle) => (
          <CycleCard
            key={cycle.billingCycle}
            cycle={cycle}
            isCurrent={isPro && !isTrialActive && billingCycle === cycle.billingCycle}
            onUpgrade={() => openUpgradeModal()}
          />
        ))}
      </div>

      {showTrialCta && (
        <div className="card p-4 mb-6 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-text">Free Trial</p>
            <p className="text-xs text-slate-dim">{trialPeriodDays} days free, no payment required.</p>
          </div>
          <button onClick={handleStartTrial} disabled={startingTrial} className="btn-ghost text-sm flex items-center gap-1.5 flex-shrink-0">
            <Sparkles size={14} />
            {startingTrial ? 'Starting\u2026' : 'Start trial'}
          </button>
        </div>
      )}

      {activeStore && (
        <>
          <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">
            Usage &middot; {activeStore.name}
          </p>
          <div className="card divide-y divide-navy-700 mb-6">
            <UsageRow icon={Package} label="Products" used={productUsage} limit={limits?.maxProductsPerStore} />
            <UsageRow icon={Users} label="Users" used={staffUsage} limit={limits?.maxUsersPerStore} />
            <UsageRow icon={Store} label="Stores (all)" used={usage?.stores ?? 1} limit={limits?.maxStores} />
            <UsageRow icon={Clock} label="History available" used={`${limits?.maxTrendHistoryDays ?? 14} days`} limit={null} />
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirmingCancel}
        title="Cancel your Pro subscription?"
        description={`You'll keep Pro features until ${currentPeriodEnd ? formatDate(currentPeriodEnd) : 'the end of your current billing period'}, then move to the Free plan. Your data stays safe either way.`}
        confirmLabel="Cancel subscription"
        cancelLabel="Never mind"
        danger
        working={working}
        onConfirm={handleCancel}
        onCancel={() => setConfirmingCancel(false)}
      />
    </div>
  )
}
