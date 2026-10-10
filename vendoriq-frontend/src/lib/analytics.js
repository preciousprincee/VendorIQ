/**
 * Product analytics (PostHog), browser side. Runs in the background for every visitor - there is no
 * opt-in step (the policies disclose it). The server sends the matching business events (sign-up,
 * verification, trial, purchase) under the same user id: see vendoriq-django/vendoriq/analytics.py.
 *
 *   1. Off entirely unless VITE_POSTHOG_KEY is set, so local dev / forks send nothing.
 *   2. People are identified by their opaque user id only - never email, phone or name. Property names that
 *      look personal are stripped from every event (BLOCKED_KEYS) as a safety net.
 *   3. No autocapture, no session recording, no cookies (localStorage persistence), and no query strings or
 *      fragments in URLs (they can hold referral codes).
 *   4. posthog-js is loaded lazily (a separate chunk), so it never delays the first paint or the till.
 *   5. Every public function swallows its own errors. Analytics must never break a sale.
 */
const KEY = import.meta.env.VITE_POSTHOG_KEY
// Default '/ingest' = same-origin reverse proxy (vercel.json), which ad-blockers rarely touch.
const HOST = import.meta.env.VITE_POSTHOG_HOST || '/ingest'
// Only used by PostHog's own UI links; not where events are sent. EU projects: https://eu.posthog.com
const UI_HOST = import.meta.env.VITE_POSTHOG_UI_HOST || 'https://us.posthog.com'

export const analyticsConfigured = Boolean(KEY)

// Keys that must never leave the device, even if a call site passes them by mistake.
const BLOCKED_KEYS = /^(e-?mail|phone|mobile|name|first_?name|last_?name|full_?name|address|password|token|customer(_?name)?|note|remark|barcode|receipt_?no)$/i

let loading = null          // Promise<posthog | null> once loading has started
let failedAt = 0            // when the library last failed to load (offline / blocked)
const RETRY_AFTER_MS = 60 * 1000
let desiredIdentity = null  // { id, props } the app wants identified (applied when PostHog is ready)
let appliedId = null

/** Strips the query string and fragment from a URL (referral codes, tokens...). */
export function stripUrl(value) {
  if (typeof value !== 'string') return value
  return value.split('#')[0].split('?')[0]
}

function clean(props) {
  const out = {}
  for (const [k, v] of Object.entries(props || {})) {
    if (BLOCKED_KEYS.test(k) || v === undefined || typeof v === 'function') continue
    out[k] = v
  }
  return out
}

function load() {
  if (!KEY) return Promise.resolve(null)
  if (loading) return loading
  // Offline: don't hammer a failing download on every event - wait a minute between attempts.
  if (failedAt && Date.now() - failedAt < RETRY_AFTER_MS) return Promise.resolve(null)
  loading = import('posthog-js')
    .then((mod) => {
      const posthog = mod.default
      posthog.init(KEY, {
        api_host: HOST,
        ui_host: UI_HOST,
        autocapture: false,
        capture_pageview: false,          // we send $pageview ourselves on route change
        capture_pageleave: false,
        disable_session_recording: true,
        disable_surveys: true,
        advanced_disable_feature_flags: true,
        person_profiles: 'identified_only',
        persistence: 'localStorage',      // no cookies
        // Last line of defence for URLs: whatever an event carries, drop query strings and fragments.
        before_send: (event) => {
          if (!event) return event
          const p = event.properties || {}
          for (const k of ['$current_url', '$referrer', '$initial_referrer', '$initial_current_url']) {
            if (p[k]) p[k] = stripUrl(p[k])
          }
          return event
        },
      })
      failedAt = 0
      return posthog
    })
    .catch(() => { loading = null; failedAt = Date.now(); return null })   // offline / blocked: retried later
  return loading
}

// Runs fn(posthog) once the library is ready. If it cannot load (offline, blocked) the call is dropped.
function withPosthog(fn) {
  if (!KEY) return
  load().then((posthog) => {
    if (!posthog) return
    try { fn(posthog) } catch { /* never break the app */ }
  })
}

function applyIdentity(posthog) {
  const want = desiredIdentity
  if (!want) {
    if (appliedId) { posthog.reset(); appliedId = null }
    return
  }
  if (appliedId !== want.id) {
    if (appliedId) posthog.reset()    // a different person on the same device: never merge them
    posthog.identify(want.id, clean(want.props))
    appliedId = want.id
  } else {
    posthog.setPersonProperties(clean(want.props))
  }
}

/**
 * Tell analytics who is signed in. `user.id` is the only identifier sent; `props` are low-cardinality
 * facts (role, plan). Call with null on sign-out. Safe to call repeatedly with the same values.
 */
export function identify(user, props) {
  try {
    desiredIdentity = user?.id ? { id: String(user.id), props } : null
    withPosthog(applyIdentity)
  } catch { /* ignore */ }
}

export const reset = () => identify(null)

export function track(event, props) {
  try {
    const safe = clean(props)
    withPosthog((ph) => ph.capture(event, safe))
  } catch { /* ignore */ }
}

export function pageview(pathname) {
  try {
    withPosthog((ph) => ph.capture('$pageview', { $current_url: stripUrl(window.location.origin + pathname), $pathname: pathname }))
  } catch { /* ignore */ }
}
