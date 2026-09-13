import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BarChart3, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'
import GoogleSignInButton from '../components/GoogleSignInButton'

export default function RegisterPage() {
  const { register, loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await register(form.name, form.email, form.password, form.phone)
      navigate('/stores')
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (idToken) => {
    setGoogleLoading(true)
    try {
      await loginWithGoogle(idToken)
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
          <div className="w-10 h-10 bg-saffron-500 rounded-xl flex items-center justify-center">
            <BarChart3 size={20} className="text-white" />
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
              <label className="label">Full name</label>
              <input className="input" placeholder="Chukwuemeka Obi" value={form.name} onChange={set('name')} required />
            </div>
            <div>
              <label className="label">Email</label>
              <input type="email" className="input" placeholder="you@example.com" value={form.email} onChange={set('email')} required autoComplete="email" />
            </div>
            <div>
              <label className="label">Phone <span className="text-slate-dim normal-case">(optional)</span></label>
              <input type="tel" className="input" placeholder="+234 800 000 0000" value={form.phone} onChange={set('phone')} />
            </div>
            <div>
              <label className="label">Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  className="input pr-10"
                  placeholder="Min. 8 characters, 1 uppercase, 1 number"
                  value={form.password}
                  onChange={set('password')}
                  required
                />
                <button type="button" onClick={() => setShowPw(v => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-dim hover:text-slate-muted">
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
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
