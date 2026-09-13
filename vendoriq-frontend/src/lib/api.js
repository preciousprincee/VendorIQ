import axios from 'axios'

// In local dev, '/api' is proxied to localhost:8000 by vite.config.js.
// In production, Vercel and Render are different domains, so the real
// backend URL must be supplied via VITE_API_URL (set in Vercel's project
// environment variables, e.g. https://vendoriq-api.onrender.com/api).
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('viq_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('viq_token')
      localStorage.removeItem('viq_user')
      localStorage.removeItem('viq_store')
      window.location.href = '/login'
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

export default api
