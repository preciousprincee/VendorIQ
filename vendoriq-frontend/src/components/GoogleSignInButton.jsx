import { useEffect, useRef } from 'react'

// Loaded once and cached - if the button appears on both Login and Register
// pages (it does), this avoids injecting the same <script> tag twice.
let scriptLoadingPromise = null
function loadGoogleScript() {
  if (window.google?.accounts?.id) return Promise.resolve()
  if (scriptLoadingPromise) return scriptLoadingPromise
  scriptLoadingPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.defer = true
    script.onload = resolve
    script.onerror = () => reject(new Error('Failed to load Google Sign-In script'))
    document.head.appendChild(script)
  })
  return scriptLoadingPromise
}

/**
 * Renders Google's own "Continue with Google" button (via their Identity
 * Services library, loaded directly - no npm package). Calls onSuccess with
 * the raw Google ID token, which the caller POSTs to
 * /api/auth/social/google/.
 *
 * Renders nothing at all if VITE_GOOGLE_CLIENT_ID isn't set, so this is
 * safe to drop into a page unconditionally - it just won't show up for
 * anyone who hasn't configured Google OAuth.
 */
export default function GoogleSignInButton({ onSuccess, onError }) {
  const containerRef = useRef(null)
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID

  useEffect(() => {
    if (!clientId) return
    let cancelled = false

    loadGoogleScript()
      .then(() => {
        if (cancelled || !containerRef.current) return
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (response) => {
            if (response?.credential) onSuccess(response.credential)
            else onError?.(new Error('Google did not return a credential.'))
          },
        })
        window.google.accounts.id.renderButton(containerRef.current, {
          theme: 'outline',
          size: 'large',
          width: 320,
          text: 'continue_with',
        })
      })
      .catch((err) => onError?.(err))

    return () => { cancelled = true }
  }, [clientId, onSuccess, onError])

  if (!clientId) return null

  return <div ref={containerRef} className="w-full flex justify-center [&>div]:!w-full" />
}
