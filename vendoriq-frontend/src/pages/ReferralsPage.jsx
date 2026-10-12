import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Copy, Share2, Gift, Wallet, Landmark, CheckCircle2, Clock, XCircle } from 'lucide-react'
import api from '../lib/api'
import { formatCurrency, formatDate, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

const STATUS_META = {
  PAID: { label: 'Paid', icon: CheckCircle2, className: 'text-brand-500' },
  PROCESSING: { label: 'Processing', icon: Clock, className: 'text-saffron-500' },
  PENDING: { label: 'Pending payout account', icon: Clock, className: 'text-slate-dim' },
  FAILED: { label: 'Failed', icon: XCircle, className: 'text-red-500' },
}

const COMMISSION_STATUS_LABEL = {
  PAID: 'Commission paid',
  PROCESSING: 'Commission processing',
  PENDING: 'Commission pending payout account',
  FAILED: 'Commission payout failed',
  REVERSED: 'Commission reversed (refunded)',
}

function BankAccountForm({ onSaved }) {
  const [banks, setBanks] = useState([])
  const [loadingBanks, setLoadingBanks] = useState(true)
  const [bankCode, setBankCode] = useState('')
  const [accountNumber, setAccountNumber] = useState('')
  const [resolvedName, setResolvedName] = useState('')
  const [resolving, setResolving] = useState(false)
  const [saving, setSaving] = useState(false)

  const [banksError, setBanksError] = useState('')

  const loadBanks = () => {
    setLoadingBanks(true)
    setBanksError('')
    api.get('/referrals/banks/')
      .then(({ data }) => {
        const list = Array.isArray(data) ? data : []
        setBanks(list)
        if (list.length === 0) setBanksError('The bank list came back empty.')
      })
      // Show the server's own reason (e.g. "payments not configured") instead
      // of a vague toast that vanishes - the dropdown used to just stay empty.
      .catch((err) => setBanksError(getErrorMessage(err) || 'Could not load the bank list.'))
      .finally(() => setLoadingBanks(false))
  }

  useEffect(() => { loadBanks() }, [])

  useEffect(() => {
    setResolvedName('')
    if (bankCode && accountNumber.length === 10) {
      let cancelled = false
      setResolving(true)
      api.post('/referrals/payout-account/resolve/', { bank_code: bankCode, account_number: accountNumber })
        .then(({ data }) => { if (!cancelled) setResolvedName(data.accountName) })
        .catch((err) => { if (!cancelled) toast.error(getErrorMessage(err)) })
        .finally(() => { if (!cancelled) setResolving(false) })
      // If bankCode/accountNumber changes again before this resolves (fast
      // typing, pasting over a previous entry, switching banks quickly),
      // this in-flight request's response must never be allowed to
      // overwrite a NEWER one that finishes first - `cancelled` blocks
      // that, so the displayed "pays out to" name always matches what's
      // currently in the two fields, not whichever request happened to
      // land last.
      return () => { cancelled = true }
    }
  }, [bankCode, accountNumber])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.post('/referrals/payout-account/', { bank_code: bankCode, account_number: accountNumber })
      toast.success('Payout account saved.')
      onSaved()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor="payout-bank" className="label">Bank</label>
        <select id="payout-bank" className="input" value={bankCode} onChange={(e) => setBankCode(e.target.value)} disabled={loadingBanks}>
          <option value="">{loadingBanks ? 'Loading banks\u2026' : 'Select your bank'}</option>
          {banks.map(b => <option key={`${b.code}-${b.name}`} value={b.code}>{b.name}</option>)}
        </select>
        {banksError && !loadingBanks && (
          <p role="alert" className="text-xs text-red-500 dark:text-red-400 mt-1.5">
            {banksError}{' '}
            <button type="button" onClick={loadBanks} className="underline font-medium">Try again</button>
          </p>
        )}
      </div>
      <div>
        <label htmlFor="payout-account-number" className="label">Account number</label>
        <input id="payout-account-number" className="input font-mono" placeholder="0123456789" maxLength={10}
          value={accountNumber} onChange={(e) => setAccountNumber(e.target.value.replace(/\D/g, ''))} />
      </div>
      {resolving && <p className="text-xs text-slate-dim">Verifying account\u2026</p>}
      {resolvedName && (
        <p className="text-xs text-brand-500">Pays out to: <span className="font-medium">{resolvedName}</span></p>
      )}
      <button onClick={handleSave} disabled={!resolvedName || saving} className="btn-primary w-full">
        {saving ? 'Saving\u2026' : 'Save payout account'}
      </button>
    </div>
  )
}

export default function ReferralsPage() {
  const navigate = useNavigate()
  const [summary, setSummary] = useState(null)
  const [commissions, setCommissions] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingBank, setEditingBank] = useState(false)

  const load = useCallback(() => {
    Promise.all([api.get('/referrals/summary/'), api.get('/referrals/commissions/')])
      .then(([summaryRes, commissionsRes]) => {
        setSummary(summaryRes.data)
        setCommissions(commissionsRes.data)
      })
      .catch((err) => toast.error(getErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const referralLink = summary ? `${window.location.origin}${summary.referralPath}` : ''

  const copyLink = () => {
    navigator.clipboard.writeText(referralLink)
    toast.success('Referral link copied')
  }
  const copyCode = () => {
    navigator.clipboard.writeText(summary.referralCode)
    toast.success('Referral code copied')
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

  if (loading) {
    return <div className="p-5 lg:p-6 max-w-xl lg:mx-auto animate-fade-in"><p className="text-sm text-slate-dim">Loading\u2026</p></div>
  }

  if (summary.needsPhone) {
    return (
      <div className="p-5 lg:p-6 max-w-xl lg:mx-auto animate-fade-in">
        <div className="flex items-center gap-2 mb-5">
          <button onClick={() => navigate('/profile')} className="text-slate-muted hover:text-slate-text">
            <ChevronLeft size={22} />
          </button>
          <h1 className="text-xl font-bold text-slate-text">Refer &amp; Earn</h1>
        </div>
        <div className="card-accent p-5">
          <div className="flex items-center gap-1.5 mb-2">
            <Gift size={14} className="text-brand-500" />
            <p className="text-sm text-slate-text font-medium">Add your phone number to get your referral code</p>
          </div>
          <p className="text-xs text-slate-dim mb-4">
            Earn {summary.commissionPercent}% of what people you refer pay on their first subscription. Your phone number becomes your referral code - other people use it to sign up under you.
          </p>
          <button onClick={() => navigate('/profile')} className="btn-primary text-sm px-4 py-2">Go to profile</button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-5 lg:p-6 max-w-xl lg:mx-auto animate-fade-in">
      <div className="flex items-center gap-2 mb-5">
        <button onClick={() => navigate('/profile')} className="text-slate-muted hover:text-slate-text">
          <ChevronLeft size={22} />
        </button>
        <h1 className="text-xl font-bold text-slate-text">Refer &amp; Earn</h1>
      </div>

      <div className="card-accent p-5 mb-5">
        <div className="flex items-center gap-1.5 mb-2">
          <Gift size={14} className="text-brand-500" />
          <p className="text-sm text-slate-text font-medium">
            Earn {summary.commissionPercent}% of what people you refer pay on their first subscription
          </p>
        </div>

        {!summary.enabled && (
          <div className="bg-saffron-500/10 border border-saffron-500/30 rounded-xl px-3 py-2.5 mb-4">
            <p className="text-xs text-saffron-500">
              This program is temporarily paused \u2014 new signups can't use a referral code right now.
              Anything you've already earned below is unaffected and still gets paid out.
            </p>
          </div>
        )}

        <p className="text-xs text-slate-dim mb-4">Share your code or link. When someone signs up and upgrades to Pro, you start earning \u2014 paid straight to your bank account.</p>

        <div className="flex items-center gap-2 mb-3">
          <div className="flex-1 bg-navy-900/40 border border-navy-700 rounded-xl px-3 py-2.5 font-mono text-sm text-slate-text tracking-wider text-center">
            {summary.referralCode}
          </div>
          <button onClick={copyCode} disabled={!summary.enabled} aria-label="Copy referral code" className="p-2.5 rounded-xl border border-navy-700 text-slate-muted hover:text-slate-text flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed">
            <Copy size={16} />
          </button>
        </div>
        <div className="flex gap-2">
          <button onClick={copyLink} disabled={!summary.enabled} className="btn-ghost flex-1 text-sm flex items-center justify-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed">
            <Copy size={14} />Copy link
          </button>
          <button onClick={share} disabled={!summary.enabled} className="btn-primary flex-1 text-sm flex items-center justify-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed">
            <Share2 size={14} />Share
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-5">
        <div className="card p-4">
          <p className="label mb-1">Paid out</p>
          <p className="text-lg font-bold font-mono text-brand-500">{formatCurrency(summary.totalPaidNgn)}</p>
        </div>
        <div className="card p-4">
          <p className="label mb-1">Pending</p>
          <p className="text-lg font-bold font-mono text-slate-text">{formatCurrency(summary.totalPendingNgn)}</p>
        </div>
      </div>

      <div className="card p-5 mb-5">
        <div className="flex items-center gap-2 mb-3">
          <Landmark size={16} className="text-slate-dim" />
          <p className="text-sm font-semibold text-slate-text">Payout account</p>
        </div>
        {summary.payoutAccount && !editingBank ? (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-text">{summary.payoutAccount.bankName}</p>
              <p className="text-xs text-slate-dim font-mono">\u2022\u2022\u2022\u2022\u2022\u2022{summary.payoutAccount.accountNumber?.slice(-4)} \u00b7 {summary.payoutAccount.accountName}</p>
            </div>
            <button onClick={() => setEditingBank(true)} className="text-xs text-brand-500 hover:underline flex-shrink-0">Change</button>
          </div>
        ) : (
          <BankAccountForm onSaved={() => { setEditingBank(false); load() }} />
        )}
      </div>

      {summary.referredUsers.length > 0 && (
        <div className="card divide-y divide-navy-700 mb-5">
          <p className="text-sm font-semibold text-slate-text px-4 pt-4 pb-2">People you've referred</p>
          {summary.referredUsers.map((r) => (
            <div key={r.id} className="px-4 py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm text-slate-text truncate">{r.name}</p>
                <p className="text-xs text-slate-dim">
                  Joined {formatDate(r.joinedAt)} \u00b7 {r.commissionStatus ? (COMMISSION_STATUS_LABEL[r.commissionStatus] || r.commissionStatus) : 'No paid subscription yet'}
                </p>
              </div>
              <p className="font-mono text-sm text-brand-500 flex-shrink-0">{formatCurrency(r.totalEarnedNgn)}</p>
            </div>
          ))}
        </div>
      )}

      {commissions.length > 0 && (
        <div className="card divide-y divide-navy-700">
          <p className="text-sm font-semibold text-slate-text px-4 pt-4 pb-2">Recent commissions</p>
          {commissions.slice(0, 20).map((c) => {
            const meta = STATUS_META[c.status] || STATUS_META.PENDING
            const Icon = meta.icon
            return (
              <div key={c.id} className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm text-slate-text truncate">{c.referredUserName}</p>
                  <p className={`text-xs flex items-center gap-1 ${meta.className}`}>
                    <Icon size={11} />{c.failureReason || meta.label}
                  </p>
                </div>
                <p className="font-mono text-sm text-slate-text flex-shrink-0">{formatCurrency(c.amountNgn)}</p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
