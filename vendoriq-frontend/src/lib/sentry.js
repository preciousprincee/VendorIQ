import * as Sentry from '@sentry/react'

// Mirrors the backend's SENTRY_DSN gating (vendoriq-django/vendoriq/settings.py):
// no DSN configured means this does nothing at all - no network calls, no
// captured data, nothing. Safe to leave unset in local dev indefinitely.
const dsn = import.meta.env.VITE_SENTRY_DSN

export const sentryEnabled = Boolean(dsn)

export function initSentry() {
  if (!dsn) return

  Sentry.init({
    dsn,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || (import.meta.env.PROD ? 'production' : 'development'),
    integrations: [Sentry.browserTracingIntegration()],
    // Performance tracing costs quota on Sentry's free tier - sampled low
    // rather than off, same reasoning as the backend's traces_sample_rate.
    tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE) || 0.1,
  })
}
