import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Check, Store, Package, Users, Clock, Sparkles } from 'lucide-react'
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
        {unlimited ? `${used} · Unlimited` : `${used}/${limit}${unit}`}
      </p>
    </div>
  )
}

function PlanCard({ code, plan, isCurrent, status, canManage, onUpgrade, onManageClick, onStartTrial, upgrading, canceling, startingTrial, showTrialCta }) {
  const isPro = code === 'PRO'
  const badgeLabel = status === 'TRIAL' ? 'Trial' : 'Current Plan'

  return (
    <div className={`card p-5 ${isCurrent && isPro ? 'border-brand-500/50' : ''}`}>
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-bold uppercase tracking-wider text-slate-text">{plan.name}</p>
        {isCurrent && <span className="badge-success">{badgeLabel}</span>}
      </div>
      <div className="flex items-baseline gap-1 mb-3">
        <p className="text-2xl font-bold font-mono text-slate-text">{formatCurrency(plan.priceNgn)}</p>
        <p className="text-xs text-slate-dim">/month</p>
      </div>
      <p className="text-xs text-slate-dim mb-4">{plan.tagline}</p>
      <div className="space-y-2 mb-5">
        {plan.includes.map((item) => (
          <div key={item} className="flex items-start gap-2">
            <Check size={14} className={`mt-0.5 flex-shrink-0 ${isPro ? 'text-brand-500' : 'text-slate-dim'}`} />
            <p className="text-xs text-slate-text">{item}</p>
          </div>
        ))}
      </div>

      {isCurrent ? (
        canManage && (
          <button onClick={onManageClick} disabled={canceling} className="btn-ghost w-full text-sm">
            {canceling ? 'Working\u2026' : 'Manage plan'}
          </button>
        )
      ) : (
        <div className="space-y-2">
          <button onClick={onUpgrade} disabled={upgrading} className="btn-primary w-full text-sm">
            {upgrading ? 'Upgrading\u2026' : `Upgrade to ${plan.name}`}
          </button>
          {showTrialCta && (
            <button onClick={onStartTrial} disabled={startingTrial} className="btn-ghost w-full text-sm flex items-center justify-center gap-1.5">
              <Sparkles size={14} />
              {startingTrial ? 'Starting\u2026' : 'Or start your free trial'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default function SubscriptionPage() {
  const navigate = useNavigate()
  const { activeStore } = useStore()
  const {
    subscription, plan, isPro, status, cancelAtPeriodEnd, currentPeriodEnd, usage, limits, plansCatalog,
    isTrialActive, trialDaysRemaining, hasUsedTrial, trialPeriodDays, viewerIsOwner, refresh,
  } = useSubscription()
  const [upgrading, setUpgrading] = useState(false)
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

  const handleUpgrade = async () => {
    setUpgrading(true)
    try {
      await api.post('/billing/upgrade/')
      toast.success("You're on Pro now \u2014 every feature is unlocked.")
      await refresh()
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
        <button onClick={() => navigate('/profile')} className="text-slate-muted hover:text-slate-text lg:hidden">
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
            <button onClick={handleUpgrade} disabled={upgrading} className="btn-primary text-sm px-4 py-2">
              {upgrading ? 'Upgrading\u2026' : 'Upgrade to Pro now'}
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

      {isPro && !isTrialActive && !cancelAtPeriodEnd && currentPeriodEnd && (
        <p className="text-xs text-slate-dim mb-5">
          Renews {formatDate(currentPeriodEnd)}.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        {plansCatalog?.map((p) => (
          <PlanCard
            key={p.code}
            code={p.code}
            plan={p}
            isCurrent={p.code === plan}
            status={status}
            canManage={p.code === plan && canManagePlan}
            onUpgrade={handleUpgrade}
            onManageClick={() => setConfirmingCancel(true)}
            onStartTrial={handleStartTrial}
            upgrading={upgrading}
            canceling={working}
            startingTrial={startingTrial}
            showTrialCta={p.code === 'PRO' && showTrialCta}
          />
        ))}
      </div>

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

      <p className="text-[11px] text-slate-dim text-center">
        This is a demo upgrade flow — no payment is collected today. A real payment provider (e.g. Paystack or Flutterwave) can be connected later without changing how plans or limits work.
      </p>

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
