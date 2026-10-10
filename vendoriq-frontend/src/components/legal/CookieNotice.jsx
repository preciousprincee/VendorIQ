import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

const DISMISSED_KEY = 'viq_cookie_notice_dismissed'

/**
 * A one-time, dismissible disclosure (not a consent gate). It says what is stored on the device and that
 * anonymous usage statistics are collected - the full detail lives in the Privacy and Cookie policies.
 */
export default function CookieNotice() {
  const [dismissed, setDismissed] = useState(true)

  useEffect(() => {
    setDismissed(localStorage.getItem(DISMISSED_KEY) === 'true')
  }, [])

  const dismiss = () => {
    localStorage.setItem(DISMISSED_KEY, 'true')
    setDismissed(true)
  }

  if (dismissed) return null

  return (
    <div role="region" aria-label="Cookie notice" className="fixed bottom-0 inset-x-0 z-50 bg-navy-800 border-t border-navy-700 px-4 py-3 sm:py-4">
      <div className="max-w-3xl mx-auto flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <p className="text-xs text-slate-muted leading-relaxed flex-1">
          We use one cookie to keep you signed in and your browser's local storage for preferences. We also collect
          anonymous usage statistics to improve VendorIQ - never your name, contact details, customers or products.
          No advertising cookies. See our{' '}
          <Link to="/legal/privacy" className="text-brand-500 hover:underline">Privacy Policy</Link> and{' '}
          <Link to="/legal/cookies" className="text-brand-500 hover:underline">Cookie Policy</Link>.
        </p>
        <button onClick={dismiss} className="btn-primary text-xs px-3 py-2 flex-shrink-0 self-end sm:self-auto">
          Got it
        </button>
      </div>
    </div>
  )
}
