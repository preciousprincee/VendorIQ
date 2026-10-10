import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'
import GoogleSignInButton from '../components/GoogleSignInButton'

export default function LoginPage() {
  const { login, loginWithGoogle } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: '', password: '' })
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await login(form.email, form.password)
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

  return (
    <div className="min-h-screen bg-navy-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm animate-fade-in">
        {/* Logo */}
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
          <h2 className="text-lg font-semibold text-slate-text mb-1">Sign in</h2>
          <p className="text-sm text-slate-muted mb-6">Welcome back. Enter your details below.</p>

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
              <label htmlFor="login-email" className="label">Email</label>
              <input
                id="login-email"
                type="email"
                className="input"
                placeholder="you@example.com"
                value={form.email}
                onChange={(e) => setForm(f => ({ ...f, email: e.target.value }))}
                required
                autoComplete="email"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="label">Password</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPw ? 'text' : 'password'}
                  className="input pr-10"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
                  required
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(v => !v)}
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-dim hover:text-slate-muted"
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full mt-2">
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-slate-muted mt-4">
          No account?{' '}
          <Link to="/register" className="text-saffron-500 hover:text-saffron-400 font-medium">
            Create one
          </Link>
        </p>
      </div>
    </div>
  )
}
