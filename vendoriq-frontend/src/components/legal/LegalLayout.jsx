import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { BUSINESS } from '../../lib/businessInfo'

/**
 * Shared shell for every legal page (Privacy, Terms, Cookie Policy, Refund
 * Policy) - consistent header/back-link/last-updated line so each policy
 * file only needs to contain its own content.
 *
 * Public route (see App.jsx: /legal/*) - reachable whether logged in or
 * not, since Terms/Privacy need to be readable *before* someone creates an
 * account, not just after.
 */
export default function LegalLayout({ title, children }) {
  const navigate = useNavigate()
  const location = useLocation()

  // "Back" goes to wherever the reader CAME FROM. It was hard-wired to
  // /welcome, which redirects a signed-in user to /stores - so opening
  // Privacy Policy from Settings and tapping Back dumped them on the store
  // picker instead of returning to Settings.
  const goBack = () => {
    const from = location.state?.from
    if (typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')) navigate(from)
    else if (window.history.state?.idx > 0) navigate(-1)
    else navigate('/welcome')
  }

  return (
    <div className="min-h-screen bg-navy-950">
      <div className="max-w-2xl mx-auto px-5 py-8 sm:py-12">
        <button type="button" onClick={goBack} className="inline-flex items-center gap-1.5 text-sm text-slate-muted hover:text-slate-text mb-6">
          <ArrowLeft size={16} /> Back
        </button>
        <h1 className="text-2xl font-bold text-slate-text mb-1">{title}</h1>
        <p className="text-xs text-slate-dim mb-8">Last updated: {BUSINESS.lastUpdated}</p>
        <div className="space-y-5">
          {children}
        </div>
        <p className="text-xs text-slate-dim mt-10 pt-6 border-t border-navy-700">
          Questions about this page? Contact us at{' '}
          <a href={`mailto:${BUSINESS.supportEmail}`} className="text-brand-500 hover:underline">{BUSINESS.supportEmail}</a>.
        </p>
      </div>
    </div>
  )
}
