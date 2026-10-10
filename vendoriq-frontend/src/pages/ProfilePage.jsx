import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Mail, Phone, Store, ChevronRight, Shield, BarChart2, ShoppingCart, Crown, Gift,
  Pencil, Copy, Share2, X, Settings, BadgeCheck, ShieldAlert, Ban, UserCheck,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useStore } from '../context/StoreContext'
import { useSubscription } from '../context/SubscriptionContext'
import BusinessFooter from '../components/legal/BusinessFooter'
import api from '../lib/api'
import { getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

const ROLE_META = {
  OWNER: { label: 'Owner', icon: Shield },
  MANAGER: { label: 'Manager', icon: BarChart2 },
  CASHIER: { label: 'Cashier', icon: ShoppingCart },
}

// Mirrors the "change phone number" warning pattern from apps that treat a
// phone number as an account identifier (OPay, banks, etc.) - shown
// whenever the person is about to set/change a phone number that ISN'T
// verified yet, since once it IS verified this stops being editable at all
// (see EditProfileForm below). Nothing here is scary for no reason - every
// line is a real consequence of this specific number becoming their
// referral code and, later, a verification/recovery number.
function PhoneChangeWarning({ hadPreviousPhone }) {
  return (
    <div className="rounded-xl border border-navy-700 bg-navy-950 overflow-hidden">
      <div className="px-4 py-3 flex items-start gap-3">
        <span className="w-7 h-7 rounded-full bg-amber-500/15 text-amber-500 flex items-center justify-center flex-shrink-0 mt-0.5"><UserCheck size={14} /></span>
        <p className="text-xs text-slate-dim leading-relaxed">This number becomes your <span className="text-slate-text font-medium">referral code</span> - it's what others use to sign up under you.</p>
      </div>
      {hadPreviousPhone && (
        <div className="px-4 py-3 flex items-start gap-3 border-t border-navy-800">
          <span className="w-7 h-7 rounded-full bg-red-500/15 text-red-500 flex items-center justify-center flex-shrink-0 mt-0.5"><Ban size={14} /></span>
          <p className="text-xs text-slate-dim leading-relaxed">Your previous number will stop working as your referral code once you save.</p>
        </div>
      )}
      <div className="px-4 py-3 flex items-start gap-3 border-t border-navy-800">
        <span className="w-7 h-7 rounded-full bg-emerald-500/15 text-emerald-500 flex items-center justify-center flex-shrink-0 mt-0.5"><ShieldAlert size={14} /></span>
        <p className="text-xs text-slate-dim leading-relaxed">You can change it as many times as you like <span className="text-slate-text font-medium">until it's verified</span>. Once verified, it can no longer be changed and may be used for login and payment verification.</p>
      </div>
      <div className="px-4 py-2.5 bg-amber-500/10 border-t border-amber-500/20">
        <p className="text-[11px] text-amber-500 font-medium leading-relaxed">Once verified, this cannot be reversed.</p>
      </div>
    </div>
  )
}

function EditProfileForm({ user, onSaved, onCancel }) {
  const { updateProfile } = useAuth()
  const [name, setName] = useState(user?.name || '')
  const [phone, setPhone] = useState(user?.phone || '')
  const [saving, setSaving] = useState(false)
  const locked = !!user?.phone_verified
  const phoneChanged = phone.trim() !== (user?.phone || '')

  const handleSave = async (e) => {
    e.preventDefault()
    if (!name.trim()) {
      toast.error('Name is required.')
      return
    }
    setSaving(true)
    try {
      await updateProfile({ name: name.trim(), phone: phone.trim() })
      toast.success('Profile updated.')
      onSaved()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSave} className="card p-5 mb-5 space-y-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-semibold text-slate-text">Edit profile</p>
        <button type="button" onClick={onCancel} aria-label="Cancel" className="text-slate-muted hover:text-slate-text p-1">
          <X size={18} />
        </button>
      </div>
      <div>
        <label className="label mb-1 block">Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} className="input w-full" placeholder="Your name" required />
      </div>
      <div>
        <label className="label mb-1 block flex items-center gap-1.5">
          Phone
          {locked && <span className="inline-flex items-center gap-1 text-[10px] normal-case tracking-normal font-semibold text-emerald-500"><BadgeCheck size={12} />Verified</span>}
        </label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className="input w-full disabled:opacity-50 disabled:cursor-not-allowed"
          placeholder="e.g. 08012345678"
          disabled={locked}
        />
        {locked ? (
          <p className="text-[11px] text-slate-dim mt-1.5">Your phone number is verified and can no longer be changed here. Contact support if you need to change it.</p>
        ) : (
          phoneChanged && <div className="mt-3"><PhoneChangeWarning hadPreviousPhone={!!user?.phone} /></div>
        )}
      </div>
      <p className="text-[11px] text-slate-dim">Your email ({user?.email}) can't be changed here - contact support if you need to update it.</p>
      <div className="flex gap-2 pt-1">
        <button type="button" onClick={onCancel} className="btn-ghost flex-1">Cancel</button>
        <button type="submit" disabled={saving} className="btn-primary flex-1">{saving ? 'Saving\u2026' : 'Save changes'}</button>
      </div>
    </form>
  )
}

function ReferralCard({ onAddPhone }) {
  const navigate = useNavigate()
  const [summary, setSummary] = useState(null)

  useEffect(() => {
    // Referral code/link are account-level (not store-level), so this
    // works even for a brand-new user who hasn't created a store yet -
    // that's the whole point of surfacing it here rather than only inside
    // /referrals (which lives under the same store-independent route now).
    api.get('/referrals/summary/').then(({ data }) => setSummary(data)).catch(() => {})
  }, [])

  if (!summary) return null
  if (!summary.enabled) return null

  if (summary.needsPhone) {
    return (
      <div className="card-accent p-5 mb-5">
        <div className="flex items-center gap-1.5 mb-1">
          <Gift size={14} className="text-brand-500" />
          <p className="text-sm text-slate-text font-medium">Add your phone number to get your referral code</p>
        </div>
        <p className="text-xs text-slate-dim mb-3">
          Earn {summary.commissionPercent}% of what people you refer pay on their first subscription. Your phone number becomes your referral code - other people use it to sign up under you.
        </p>
        <button onClick={onAddPhone} className="btn-primary text-sm px-4 py-2">Add phone number</button>
      </div>
    )
  }

  const referralLink = `${window.location.origin}${summary.referralPath}`

  const copyCode = () => {
    navigator.clipboard.writeText(summary.referralCode)
    toast.success('Referral code copied')
  }
  const copyLink = () => {
    navigator.clipboard.writeText(referralLink)
    toast.success('Referral link copied')
  }
  const share = () => {
    const text = `Join me on VendorIQ and manage your store the smart way \u2014 use my code ${summary.referralCode} or this link: ${referralLink}`
    if (navigator.share) {
      navigator.share({ text }).catch(() => {})
    } else {
      navigator.clipboard.writeText(text)
      toast.success('Referral message copied to share')
    }
  }

  return (
    <div className="card-accent p-5 mb-5">
      <div className="flex items-center gap-1.5 mb-2">
        <Gift size={14} className="text-brand-500" />
        <p className="text-sm text-slate-text font-medium">
          Earn {summary.commissionPercent}% of what people you refer pay on their first subscription
        </p>
      </div>
      <p className="text-[11px] text-slate-dim mb-2">Your referral code is your phone number.</p>
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 bg-navy-900/40 border border-navy-700 rounded-xl px-3 py-2.5 font-mono text-sm text-slate-text tracking-wider text-center">
          {summary.referralCode}
        </div>
        <button onClick={copyCode} aria-label="Copy referral code" className="p-2.5 rounded-xl border border-navy-700 text-slate-muted hover:text-slate-text flex-shrink-0">
          <Copy size={16} />
        </button>
      </div>
      <div className="flex gap-2 mb-3">
        <button onClick={copyLink} className="btn-ghost flex-1 text-sm flex items-center justify-center gap-1.5">
          <Copy size={14} />Copy link
        </button>
        <button onClick={share} className="btn-primary flex-1 text-sm flex items-center justify-center gap-1.5">
          <Share2 size={14} />Share
        </button>
      </div>
      <button onClick={() => navigate('/referrals')} className="text-xs text-slate-dim hover:text-slate-muted flex items-center gap-1 mx-auto">
        View earnings &amp; payout account<ChevronRight size={12} />
      </button>
    </div>
  )
}

export default function ProfilePage() {
  const { user } = useAuth()
  const { activeStore, clearStore } = useStore()
  const { isPro, isTrialActive, trialDaysRemaining } = useSubscription()
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)

  const handleSwitchStore = () => { clearStore(); navigate('/stores') }
  const roleMeta = activeStore ? (ROLE_META[activeStore.role] || ROLE_META.CASHIER) : null

  return (
    <div className="p-5 lg:p-6 max-w-lg lg:mx-auto animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Profile</h1>
        <button
          onClick={() => navigate('/settings')}
          aria-label="Settings"
          className="w-9 h-9 rounded-full flex items-center justify-center text-slate-muted hover:text-slate-text hover:bg-navy-700 transition-colors flex-shrink-0"
        >
          <Settings size={19} />
        </button>
      </div>

      {editing ? (
        <EditProfileForm user={user} onSaved={() => setEditing(false)} onCancel={() => setEditing(false)} />
      ) : (
        <div className="card p-5 flex items-center gap-4 mb-5">
          <div className="w-14 h-14 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0">
            <span className="text-xl font-bold text-brand-600 dark:text-brand-400">{user?.name?.[0]?.toUpperCase()}</span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold text-slate-text truncate">{user?.name}</p>
            <p className="text-xs text-slate-dim truncate">{user?.email}</p>
          </div>
          <button onClick={() => setEditing(true)} aria-label="Edit profile" className="p-2 rounded-xl border border-navy-700 text-slate-muted hover:text-slate-text flex-shrink-0">
            <Pencil size={15} />
          </button>
        </div>
      )}

      <div className="card divide-y divide-navy-700 mb-5">
        <div className="px-4 py-3 flex items-center gap-3">
          <Mail size={16} className="text-slate-dim flex-shrink-0" />
          <div className="min-w-0">
            <p className="label mb-0.5">Email</p>
            <p className="text-sm text-slate-text truncate">{user?.email}</p>
          </div>
        </div>
        {user?.phone && (
          <div className="px-4 py-3 flex items-center gap-3">
            <Phone size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="label mb-0.5">Phone</p>
              <p className="text-sm text-slate-text truncate">{user.phone}</p>
            </div>
            {user.phone_verified ? (
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-500 flex-shrink-0"><BadgeCheck size={13} />Verified</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-dim flex-shrink-0">Unverified</span>
            )}
          </div>
        )}
        {activeStore && (
          <button onClick={handleSwitchStore} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
            <Store size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="label mb-0.5">Active store</p>
              <p className="text-sm text-slate-text truncate">
                {activeStore.name}
                {roleMeta && <span className="text-slate-dim"> · {roleMeta.label}</span>}
              </p>
            </div>
            <ChevronRight size={16} className="text-slate-dim flex-shrink-0" />
          </button>
        )}
        {!activeStore && (
          <button onClick={() => navigate('/stores')} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
            <Store size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="label mb-0.5">Stores</p>
              <p className="text-sm text-slate-text truncate">Create or switch to a store</p>
            </div>
            <ChevronRight size={16} className="text-slate-dim flex-shrink-0" />
          </button>
        )}
      </div>

      {activeStore?.role === 'OWNER' && (
        <div className="card mb-5">
          <button onClick={() => navigate('/subscription')} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
            <Crown size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="label mb-0.5">Subscription &amp; billing</p>
              <p className="text-sm text-slate-text truncate">
                {isTrialActive
                  ? `Trial · ${trialDaysRemaining} day${trialDaysRemaining === 1 ? '' : 's'} left`
                  : isPro ? 'Pro plan' : 'Free plan'}
                {!isPro && <span className="text-brand-500 font-medium"> · Upgrade</span>}
              </p>
            </div>
            <ChevronRight size={16} className="text-slate-dim flex-shrink-0" />
          </button>
        </div>
      )}

      <ReferralCard onAddPhone={() => setEditing(true)} />

      <BusinessFooter compact />
    </div>
  )
}
