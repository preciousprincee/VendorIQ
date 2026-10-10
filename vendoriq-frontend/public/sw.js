// Bump this on any change to the strategy below - a new name makes every
// existing install drop the old cache on activate.
const CACHE_NAME = 'vendoriq-v4'
const SHELL = '/index.html'

// Install - precache just the app shell for offline use.
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.add(SHELL)))
  self.skipWaiting()
})

// Activate - clean up old caches.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

// Fetch strategy:
// - API calls:      not touched by the worker (real network errors must reach the app)
// - Page loads:     NETWORK FIRST, cached shell only when offline. This used to
//                   be cache-first, which pinned every returning user to the
//                   index.html (and therefore the JS bundle) from their first
//                   visit - deployed fixes never reached installed users.
// - Hashed assets:  cache first (/assets/* filenames change with their content,
//                   so a cached copy can never be stale). /icons/* (logo) is
//                   cached too so the app looks right offline.
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Skip non-GET and chrome-extension requests
  if (request.method !== 'GET' || url.protocol === 'chrome-extension:') return

  // API calls are NOT intercepted at all. The worker used to answer a failed
  // API request with a made-up "503 You are offline" response - which turned a
  // genuine network failure into what looks like a server error, so the app
  // could never tell "no connection" (queue the sale, show the offline banner)
  // from "the server had a problem". A real network failure must reach the
  // page as a network failure.
  if (url.pathname.startsWith('/api')) return

  // Only manage our own origin (Paystack's script, Google sign-in, fonts etc. go straight to the network).
  if (url.origin !== self.location.origin) return

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response && response.status === 200) {
            const clone = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(SHELL, clone))
          }
          return response
        })
        .catch(() => caches.match(SHELL))
    )
    return
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached
      return fetch(request).then((response) => {
        if (response && response.status === 200 && (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/'))) {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
        }
        return response
      })
    })
  )
})
