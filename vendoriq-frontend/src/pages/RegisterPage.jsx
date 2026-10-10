import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../lib/utils'
import api from '../lib/api'
import toast from 'react-hot-toast'
import GoogleSignInButton from '../components/GoogleSignInButton'

export default function RegisterPage() {
  const { register, loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // A referral link (vendoriq.app/register?ref=CODE) pre-fills this; anyone
  // else can type a code in directly - see apps/referrals for what this feeds.
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', referralCode: searchParams.get('ref') || '' })
  const [showPw, setShowPw] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  // Whether the referral program is currently switched on (Django Admin >
  // Referrals > Referral settings) - checked here specifically because
  // this page is public/unauthenticated, so it can't just read it off an
  // already-logged-in user's data the way ReferralsPage does. Defaults to
  // hidden until the check resolves, rather than flashing the field and
  // then yanking it away if the program turns out to be off.
  const [referralsEnabled, setReferralsEnabled] = useState(false)

  useEffect(() => {
    api.get('/referrals/status/')
      .then(({ data }) => setReferralsEnabled(data.enabled))
      .catch(() => {}) // fails closed - field just stays hidden, registration itself is unaffected either way
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!agreed) {
      toast.error('Please agree to the Terms & Conditions and Privacy Policy to continue.')
      return
    }
    setLoading(true)
    try {
      await register(form.name, form.email, form.password, form.phone, referralsEnabled ? form.referralCode : '')
      navigate('/verify')
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (idToken) => {
    setGoogleLoading(true)
    try {
      await loginWithGoogle(idToken, referralsEnabled ? form.referralCode : '')
      navigate('/stores')
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setGoogleLoading(false)
    }
  }

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }))

  return (
    <div className="min-h-screen bg-navy-900 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-sm animate-fade-in">
        <div className="flex items-center gap-3 justify-center mb-10">
          <div className="w-10 h-10 rounded-xl overflow-hidden flex items-center justify-center flex-shrink-0">
            <img src="/icons/logo.png" alt="VendorIQ" className="w-full h-full object-contain" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-text leading-none">VendorIQ</h1>
            <p className="text-xs text-slate-dim mt-0.5">Smart business intelligence</p>
          </div>
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-semibold text-slate-text mb-1">Create account</h2>
          <p className="text-sm text-slate-muted mb-6">Start tracking your business the smart way.</p>

          <div className="mb-5">
            <GoogleSignInButton onSuccess={handleGoogleSuccess} onError={() => toast.error('Google sign-in failed. Try again or use your email.')} />
            {googleLoading && <p className="text-xs text-slate-dim text-center mt-2">Signing in...</p>}
          </div>

          <div className="relative mb-5">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-navy-700" /></div>
            <div className="relative flex justify-center text-xs"><span className="bg-navy-800 px-2 text-slate-dim">or</span></div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="reg-name" className="label">Full name</label>
              <input id="reg-name" className="input" placeholder="Chukwuemeka Obi" value={form.name} onChange={set('name')} required autoComplete="name" />
            </div>
            <div>
              <label htmlFor="reg-email" className="label">Email</label>
              <input id="reg-email" type="email" className="input" placeholder="you@example.com" value={form.email} onChange={set('email')} required autoComplete="email" />
            </div>
            <div>
              <label htmlFor="reg-phone" className="label">Phone number</label>
              <input id="reg-phone" type="tel" className="input" placeholder="+234 800 000 0000" value={form.phone} onChange={set('phone')} autoComplete="tel" required />
              <p className="text-[11px] text-slate-dim mt-1">We'll text you a code to verify it.</p>
            </div>
            {referralsEnabled && (
              <div>
                <label htmlFor="reg-referral" className="label">Referred by <span className="text-slate-dim normal-case">(optional)</span></label>
                <input id="reg-referral" type="tel" className="input" placeholder="Referrer's phone number, e.g. 08012345678" value={form.referralCode}
                  onChange={(e) => setForm(f => ({ ...f, referralCode: e.target.value }))} />
              </div>
            )}
            <div>
              <label htmlFor="reg-password" className="label">Password</label>
              <div className="relative">
                <input
                  id="reg-password"
                  type={showPw ? 'text' : 'password'}
                  className="input pr-10"
                  placeholder="Min. 8 characters, 1 uppercase, 1 number"
                  value={form.password}
                  onChange={set('password')}
                  required
                  autoComplete="new-password"
                />
                <button type="button" onClick={() => setShowPw(v => !v)} aria-label={showPw ? 'Hide password' : 'Show password'} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-dim hover:text-slate-muted">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <label htmlFor="reg-agree" className="flex items-start gap-2.5 pt-1 cursor-pointer">
              <input
                id="reg-agree"
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                required
                className="mt-0.5 w-4 h-4 rounded border-navy-600 text-brand-500 focus:ring-brand-500 flex-shrink-0"
              />
              <span className="text-xs text-slate-muted leading-relaxed">
                I agree to VendorIQ's{' '}
                <Link to="/legal/terms" target="_blank" rel="noopener noreferrer" className="text-brand-500 hover:underline">Terms &amp; Conditions</Link>
                {' '}and{' '}
                <Link to="/legal/privacy" target="_blank" rel="noopener noreferrer" className="text-brand-500 hover:underline">Privacy Policy</Link>,
                {' '}and consent to my data being processed as described there.
              </span>
            </label>

            <button type="submit" disabled={loading || !agreed} className="btn-primary w-full mt-2">
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-slate-muted mt-4">
          Already have an account?{' '}
          <Link to="/login" className="text-saffron-500 hover:text-saffron-400 font-medium">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
