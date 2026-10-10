import axios from 'axios'
import {
  getAccessToken, setAccessToken, hasSessionHint, dropLegacyTokens, wipeLocalSession, sessionEpoch,
} from './session'

// In local dev, '/api' is proxied to localhost:8000 by vite.config.js.
// In production, Vercel and Render are different domains, so the real
// backend URL must be supplied via VITE_API_URL (set in Vercel's project
// environment variables, e.g. https://vendoriq-api.onrender.com/api).
// Cross-origin only when VITE_API_URL points at a different site (hosting shape B in the
// backend settings). The recommended same-origin setup leaves it unset and proxies /api.
const CROSS_ORIGIN = !!import.meta.env.VITE_API_URL

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 15000,
  withCredentials: CROSS_ORIGIN,   // lets the browser send the HttpOnly session cookie cross-origin
})

// Cookie-authenticated endpoints must carry this header. A foreign website cannot add a custom
// header to a request without a CORS preflight the server refuses, so this stops cross-site abuse.
const CSRF_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' }
const AUTH_ENDPOINT = /\/auth\/(login|register|social\/google|token\/refresh|logout)\/?$/

api.interceptors.request.use(async (config) => {
  const url = config.url || ''
  // After a reload the access token (memory only) is gone. If someone is signed in, quietly get a new
  // one from the cookie BEFORE the request goes out. Offline this fails harmlessly and the request
  // simply proceeds - it will fail as a network error, which the offline layer already handles.
  if (!AUTH_ENDPOINT.test(url) && !getAccessToken() && hasSessionHint()) {
    try { await refreshAccessToken() } catch { /* offline, or the session has ended: the 401 path below handles it */ }
  }
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// --- network state ----------------------------------------------------------
// `navigator.onLine` only says whether there is a network INTERFACE (wifi
// with no internet still reports true), so the app also learns from real
// requests: a request that never got an HTTP answer means "down", any HTTP
// answer (even a 500) means "reachable". The offline layer listens for this.
let networkDown = false
function setNetworkDown(down) {
  if (networkDown === down) return
  networkDown = down
  window.dispatchEvent(new CustomEvent('viq:network', { detail: { down } }))
}

/** Whether the last request that reached (or failed to reach) the server says we are offline. */
export const isNetworkDown = () => networkDown

/** True when the request never reached the server (no HTTP response at all). */
export const isNetworkError = (err) => !!err && !err.response && err.code !== 'ERR_CANCELED'

// --- silent session refresh -------------------------------------------------
// Access tokens are short-lived (1 hour). When one expires the API answers
// 401; instead of logging the person out we trade the long-lived refresh
// token for a new access token and replay the request - once. Several
// requests failing at the same moment share ONE refresh call.
let refreshPromise = null
let refreshEpoch = -1

function clearSessionAndGoToLogin() {
  wipeLocalSession()
  if (window.location.pathname !== '/login') window.location.href = '/login'
}

/**
 * Get a fresh access token using the HttpOnly cookie (the browser attaches it; this code never sees it).
 * Resolves with the token, or rejects: with a NETWORK error when offline (the session is still fine - do not
 * sign out), or with an HTTP error when the server refused the session (it has ended).
 */
export function refreshAccessToken() {
  // Share an in-flight refresh - but only one that started under the CURRENT identity.
  if (refreshPromise && refreshEpoch === sessionEpoch()) return refreshPromise

  // Sessions from before cookies existed still hold their refresh token in localStorage: send it
  // once so the server moves it into the cookie, then forget it.
  const legacy = localStorage.getItem('viq_refresh')
  const startedAt = sessionEpoch()
  // Plain axios (not `api`) so this call can't recurse into the interceptors.
  const promise = axios
    .post(`${api.defaults.baseURL}/auth/token/refresh/`, legacy ? { refresh: legacy } : {}, {
      timeout: 15000, withCredentials: true, headers: CSRF_HEADERS,
    })
    .then(({ data }) => {
      if (sessionEpoch() !== startedAt) {
        // Signed out / switched account while this was in flight: the token is for someone else now.
        const stale = new Error('Session changed during refresh')
        stale.sessionChanged = true
        throw stale
      }
      setAccessToken(data.token)
      dropLegacyTokens()
      return data.token
    })
    .finally(() => {
      if (refreshPromise === promise) { refreshPromise = null; refreshEpoch = -1 }
    })
  refreshPromise = promise
  refreshEpoch = startedAt
  return promise
}

api.interceptors.response.use(
  (res) => { setNetworkDown(false); return res },
  async (err) => {
    if (isNetworkError(err)) setNetworkDown(true)
    else if (err.response) setNetworkDown(false)
    // A 401 from the login/register/Google/refresh/logout endpoints just means "wrong credentials" or
    // "no session" - not "your session expired". Reloading /login there used to wipe the page (and the
    // error toast) the instant a login failed, so people never saw "Invalid email or password".
    const url = err.config?.url || ''
    if (err.response?.status === 401 && !AUTH_ENDPOINT.test(url)) {
      const original = err.config
      if (original && !original._retried && hasSessionHint()) {
        original._retried = true
        let token = null
        try {
          token = await refreshAccessToken()
        } catch (refreshErr) {
          // No connection to confirm the session: that is NOT a sign-out. Stay signed in; this
          // request fails like any other offline request and the offline layer takes over.
          if (isNetworkError(refreshErr) || refreshErr?.sessionChanged) return Promise.reject(err)
          // Likewise if the identity changed mid-refresh: wiping now would sign out the NEW user.
          // Otherwise the server refused the cookie (expired, revoked, password changed): sign out.
        }
        // Replay OUTSIDE the try above: whatever the replayed request answers (even an error like a
        // 400) is that request's real result - only a failed REFRESH means "signed out".
        if (token) {
          original.headers = { ...original.headers, Authorization: `Bearer ${token}` }
          return api(original)
        }
      }
      clearSessionAndGoToLogin()
    }
    // Every Pro-gated endpoint (see apps/billing/exceptions.py::UpgradeRequired
    // on the backend) responds 402 with {error, code, feature, title,
    // upgradeRequired}. Broadcasting it as a window event - rather than
    // requiring every page to know about the upgrade modal - means any
    // gated action anywhere in the app opens the same upgrade experience
    // automatically, without each page wiring it up by hand.
    // SubscriptionContext listens for this and opens the modal; the
    // rejected promise still propagates so a page's own catch/toast runs
    // too, for a quick inline message alongside the fuller modal.
    //
    // Passive/background requests (e.g. a secondary "also show this Pro
    // card if available" fetch on page load) should NOT pop the modal
    // unprompted - that reads as an aggressive interstitial, not the
    // "tasteful lock state" the product calls for. Those call sites pass
    // `{ skipUpgradeModal: true }` in the request config to opt out; the
    // page then renders its own inline <UpgradePrompt>/<FeatureGate>
    // instead. Explicit user actions (clicking "Add product", "Export
    // records", "New invoice") leave this on, which is the common case.
    if (err.response?.status === 402 && err.response?.data?.upgradeRequired && !err.config?.skipUpgradeModal) {
      window.dispatchEvent(new CustomEvent('viq:upgrade-required', { detail: err.response.data }))
    }
    return Promise.reject(err)
  }
)

export { CSRF_HEADERS }
export default api
