import { useState, useEffect, useRef } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Mail, Phone, CheckCircle2, LogOut } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { useStore } from '../context/StoreContext'
import api from '../lib/api'
import { getErrorMessage } from '../lib/utils'

// One "send a code, then type it in" card - used for both email and phone.
function CodeStep({ icon: Icon, title, description, done, sendPath, confirmPath, onVerified, beforeSend, sendLabel = 'Send code', extra }) {
  const [code, setCode] = useState('')
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [cooldown, setCooldown] = useState(0)
  const [debugCode, setDebugCode] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  const send = async () => {
    setError('')
    const extraBody = beforeSend ? beforeSend() : {}
    if (extraBody === null) return // the caller showed its own validation message
    setSending(true)
    try {
      const { data } = await api.post(sendPath, extraBody)
      if (data.alreadyVerified) { onVerified(data.user); return }
      if (data.user) onVerified(data.user, { stillPending: true })
      setSent(true)
      setCode('')
      setCooldown(data.cooldown || 60)
      setDebugCode(data.debugCode || '')
      toast.success('Code sent')
    } catch (err) {
      const retry = err.response?.data?.retryAfter
      if (retry) { setSent(true); setCooldown(retry) }
      setError(getErrorMessage(err))
    } finally {
      setSending(false)
    }
  }

  const confirm = async (e) => {
    e.preventDefault()
    if (code.length !== 6) { setError('Enter the 6-digit code.'); return }
    setError('')
    setConfirming(true)
    try {
      const { data } = await api.post(confirmPath, { code })
      toast.success('Verified')
      onVerified(data.user)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="card p-4 mb-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-8 h-8 rounded-lg bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0">
          {done ? <CheckCircle2 size={17} className="text-green-500" /> : <Icon size={16} className="text-brand-500" />}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-text">{title}</p>
          <p className="text-xs text-slate-dim truncate">{done ? 'Verified' : description}</p>
        </div>
      </div>

      {!done && (
        <>
          {extra}
          {!sent ? (
            <button type="button" onClick={send} disabled={sending} className="btn-primary w-full mt-2">
              {sending ? 'Sending\u2026' : sendLabel}
            </button>
          ) : (
            <form onSubmit={confirm} className="mt-2 space-y-2">
              <input
                className="input text-center font-mono text-lg tracking-[0.4em]" inputMode="numeric" autoComplete="one-time-code"
                maxLength={6} placeholder="------" value={code} aria-label="6-digit code"
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              />
              {debugCode && <p className="text-[11px] text-amber-500 text-center">Dev mode - your code is {debugCode}</p>}
              <button type="submit" disabled={confirming || code.length !== 6} className="btn-primary w-full">
                {confirming ? 'Checking\u2026' : 'Verify'}
              </button>
              <button type="button" onClick={send} disabled={sending || cooldown > 0}
                className="w-full text-xs text-slate-muted hover:text-slate-text disabled:opacity-50">
                {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
              </button>
            </form>
          )}
          {error && <p role="alert" className="text-xs text-red-500 dark:text-red-400 mt-2">{error}</p>}
        </>
      )}
    </div>
  )
}

export default function VerifyPage() {
  const { user, applyUser, logout } = useAuth()
  const { clearStore } = useStore()
  const navigate = useNavigate()
  const [phone, setPhone] = useState(user?.phone || '')
  const redirected = useRef(false)

  // Whatever the cached copy says, ask the server - someone who verified on
  // another device shouldn't be stuck here.
  useEffect(() => {
    api.get('/auth/me/').then(({ data }) => applyUser(data.user)).catch(() => {})
  }, [applyUser])

  const allVerified = !!user && !user.needs_verification
  // A toast is a side effect - fire it from an effect, not during render
  // (React warns about updating the toaster while rendering this component).
  useEffect(() => {
    if (allVerified && !redirected.current) {
      redirected.current = true
      toast.success("You're all set")
    }
  }, [allVerified])

  if (!user) return <Navigate to="/welcome" replace />
  if (allVerified) return <Navigate to="/stores" replace />

  const handleLogout = () => { clearStore(); logout(); navigate('/login') }

  return (
    <div className="min-h-screen flex items-center justify-center p-5 bg-navy-950">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="w-10 h-10 rounded-xl overflow-hidden flex items-center justify-center mb-4">
          <img src="/icons/logo.png" alt="VendorIQ" className="w-full h-full object-contain" />
        </div>
        <h1 className="text-xl font-bold text-slate-text mb-1">Verify your account</h1>
        <p className="text-sm text-slate-muted mb-5">
          Confirm your email and phone number to start your free trial and keep your account secure.
        </p>

        <CodeStep
          icon={Mail} title="Email address" description={user.email} done={user.email_verified}
          sendPath="/auth/verify/email/send/" confirmPath="/auth/verify/email/confirm/"
          onVerified={(u) => applyUser(u)}
        />

        <CodeStep
          icon={Phone} title="Phone number" description={user.phone || 'Add your phone number'} done={user.phone_verified}
          sendPath="/auth/verify/phone/send/" confirmPath="/auth/verify/phone/confirm/"
          onVerified={(u) => applyUser(u)}
          extra={
            <div className="mt-1">
              <label htmlFor="verify-phone" className="label">Phone number</label>
              <input id="verify-phone" type="tel" className="input" placeholder="0801 234 5678" autoComplete="tel"
                value={phone} onChange={e => setPhone(e.target.value)} />
            </div>
          }
          beforeSend={() => {
            if (!phone.trim()) { toast.error('Enter your phone number first.'); return null }
            return { phone: phone.trim() }
          }}
        />

        <button onClick={handleLogout} className="mx-auto flex items-center gap-1.5 text-xs text-slate-dim hover:text-slate-muted">
          <LogOut size={13} />Sign out
        </button>
      </div>
    </div>
  )
}
