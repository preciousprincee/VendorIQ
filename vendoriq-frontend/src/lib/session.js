import { wipeOfflineCaches } from './offline/cleanup'
/**
 * Where the sign-in state lives, and what a page script can and cannot see.
 *
 *   ACCESS TOKEN  (short-lived, ~1 h)   in MEMORY ONLY. Lost on reload; the app simply
 *                                        gets a new one from the refresh cookie.
 *   REFRESH TOKEN (30 days)             in an HttpOnly cookie set by the server. Scripts
 *                                        cannot read it - that is the whole point.
 *   SESSION HINT  (non-secret)          localStorage `viq_user`: who was signed in last
 *                                        (name, role...). It is what lets the app open
 *                                        offline, straight into the till, without any
 *                                        server call. It grants no access by itself - every
 *                                        API request still needs a token the server accepts.
 */
let accessToken = null

// Bumped whenever the signed-in identity changes (sign-in, sign-out). A token refresh that was already
// in flight when that happened belongs to the OLD identity and must not be stored: otherwise signing out
// (or switching account) while a refresh is pending would resurrect the old user's access token.
let epoch = 0
export const sessionEpoch = () => epoch
export const invalidatePendingRefresh = () => { epoch += 1 }

export const getAccessToken = () => accessToken
export const setAccessToken = (token) => { accessToken = token || null }

export const hasSessionHint = () => {
  try { return !!localStorage.getItem('viq_user') } catch { return false }
}

/** Tokens that older versions of the app kept in localStorage, readable by any script. */
export const LEGACY_KEYS = ['viq_token', 'viq_refresh']
export const dropLegacyTokens = () => LEGACY_KEYS.forEach((k) => localStorage.removeItem(k))

// Set when signing out could not reach the server (offline): the cookie is still valid, so
// tell the server to clear it the next time there is a connection.
const LOGOUT_PENDING = 'viq_logout_pending'
export const markLogoutPending = () => localStorage.setItem(LOGOUT_PENDING, '1')
export const isLogoutPending = () => localStorage.getItem(LOGOUT_PENDING) === '1'
export const clearLogoutPending = () => localStorage.removeItem(LOGOUT_PENDING)

export function wipeLocalSession() {
  invalidatePendingRefresh()
  wipeOfflineCaches()   // fire and forget: customer data cached for offline use must not outlive the session
  setAccessToken(null)
  dropLegacyTokens()
  ;['viq_user', 'viq_store'].forEach((k) => localStorage.removeItem(k))
  sessionStorage.removeItem('viq_account_only')
}
