import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { track } from '../lib/analytics'

/**
 * PWA install state, shared by the floating install banner and the
 * "Install app" row in Settings.
 *
 * The browser fires `beforeinstallprompt` ONCE, early, and never again - so
 * the listener has to live at the very top of the app (this provider is
 * mounted in main.jsx). When it lived inside the banner component, anything
 * else that wanted to offer installation (Settings) never got the event.
 */
const InstallContext = createContext(null)

const isStandalone = () =>
  window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true

export function InstallProvider({ children }) {
  const [deferredPrompt, setDeferredPrompt] = useState(null)
  const [installed, setInstalled] = useState(isStandalone)
  const [bannerDismissed, setBannerDismissed] = useState(false)

  useEffect(() => {
    const onBeforeInstall = (e) => { e.preventDefault(); setDeferredPrompt(e) }
    const onInstalled = () => { setInstalled(true); setDeferredPrompt(null) }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

  // Resolves to 'accepted' | 'dismissed' | 'unavailable'.
  const promptInstall = useCallback(async () => {
    if (!deferredPrompt) return 'unavailable'
    deferredPrompt.prompt()
    const { outcome } = await deferredPrompt.userChoice
    // A prompt event can only be used once.
    setDeferredPrompt(null)
    if (outcome === 'accepted') { setInstalled(true); track('install_prompt_accepted') }
    return outcome
  }, [deferredPrompt])

  const ua = window.navigator.userAgent || ''
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (ua.includes('Mac') && 'ontouchend' in document)

  return (
    <InstallContext.Provider value={{
      canInstall: !!deferredPrompt, installed, isIOS, promptInstall,
      bannerDismissed, dismissBanner: () => setBannerDismissed(true),
    }}>
      {children}
    </InstallContext.Provider>
  )
}

export const useInstall = () => {
  const ctx = useContext(InstallContext)
  if (!ctx) throw new Error('useInstall must be used within InstallProvider')
  return ctx
}
