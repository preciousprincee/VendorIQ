# Handoff - where work stopped

Everything below is accurate to the code in this zip. Nothing Django-side or `npm`-side could be executed in this sandbox (no network, no Django) - see "Never executed".

## Done this session
1. **Reviewed the HttpOnly-cookie session work** (backend `cookies.py`/`views.py`/settings, frontend `session.js`/`api.js`/`AuthContext.jsx`). Fixed:
   - refresh-vs-sign-out/sign-in race (stale refresh could restore the old user's access token) via an identity epoch in `lib/session.js`; 401 handler no longer signs out a *new* user because of an *old* request.
   - cookie notice + Cookie Policy wrongly said "no cookies"; stale CORS comment corrected.
2. **PostHog analytics - browser AND server, always on (no consent step, by product decision).**
   - Browser: `src/lib/analytics.js`, `AnalyticsBridge` in `App.jsx` (identify by user id + role/plan, `$pageview`), UI events at their call sites. `posthog-js` in `package.json`; `VITE_POSTHOG_*` in `vendoriq-frontend/.env.example`.
   - Server: `vendoriq/analytics.py` (`posthog` in `requirements.txt`; `POSTHOG_API_KEY` / `POSTHOG_HOST` in settings, `.env.example`, `render.yaml` for web + worker). Events `sign_up`, `email_verified`, `phone_verified`, `trial_started`, `subscription_purchased` (inside `create_subscription_purchase`, so verify call and webhook share one count). Tests: `apps/authentication/test_server_analytics.py`.
   - Consent banner / Settings switch removed; `CookieNotice` is a plain disclosure; Privacy + Cookie policies rewritten accordingly. **Have a lawyer check the no-opt-in approach** (GDPR/ePrivacy for EU/UK visitors, NDPA).
   - `GoogleLoginView` returns `isNewAccount` (created <20 s ago).
3. `AUDIT_REPORT.md` has a Round 7 entry; its setup step now says `NUM_PROXIES=2`.

## Still NOT done
- `VendorIQ-System-Design.pdf` (v1.1) still calls section 10.4 an *option*; regenerate (ReportLab script is not in this zip) and add: cookie sessions implemented, analytics + consent design, the decision above.
- Offline PIN lock screen / auto sign-out after N days offline (recommended earlier, not built).
- No server-side token blacklist: "sign out everywhere" = change password.

## Never executed - run before deploying
`pip install -r requirements-dev.txt && pytest` (pytest-django's `django_capture_on_commit_callbacks` fixture is used by the new tests), `python manage.py migrate`, `python manage.py makemigrations --check`, `npm install && npm run build`.
New migrations: authentication 0004 + 0005 (LoginEvent table - was missing entirely), billing 0008, ai 0003, notifications 0001+0002, customers 0001, sales 0002, products 0003.
Executed here against fakes and passing: browser analytics logic, session/refresh logic incl. both race cases (7 scenarios), parse + undefined-name/relative-import check of all 69 frontend files, `py_compile` of backend.

## Deploy checklist
Cookie change (unchanged from before):
1. Vercel: leave `VITE_API_URL` **unset** (cross-origin would stop the cookie being sent).
2. Confirm `vercel.json`'s destination is the real Render URL (`https://vendoriq-api.onrender.com` is a guess) and that Vercel's proxy timeout covers AI chat / Render cold starts.
3. **Check that trailing slashes survive the Vercel rewrite** (Django has `APPEND_SLASH=False` and every route ends in `/`): after deploy, sign in and confirm `/api/auth/login/` returns 200, not 404.
4. Render: `NUM_PROXIES=2`, `AUTH_ALLOW_BODY_REFRESH=True` (set False 30 days later).
5. In dev tools after sign-in: cookie `viq_refresh` is HttpOnly + Secure + SameSite=Lax, path `/api/auth/`; localStorage has no `viq_token`/`viq_refresh`; reload keeps you signed in; offline the till still opens and sells.

Analytics (optional):
6. Set `VITE_POSTHOG_KEY` on Vercel and `POSTHOG_API_KEY` on Render (API + worker) - the SAME project key (`phc_...`). EU project: change both `/ingest` destinations in `vercel.json` to `eu.i.posthog.com` / `eu-assets.i.posthog.com`, set `VITE_POSTHOG_UI_HOST=https://eu.posthog.com` and `POSTHOG_HOST=https://eu.i.posthog.com`.
7. Test: open the app - `/ingest/e/` requests appear; register -> one `sign_up`; verify email/phone -> one event each; start a trial -> `trial_started`; pay in Paystack test mode -> exactly one `subscription_purchased` (also if you close the tab before the verify call and let the webhook land); no event contains names, emails or phone numbers.

## Going live with Paystack (checklist)
1. Paystack dashboard in LIVE mode: business activated; copy BOTH `sk_live_...` and `pk_live_...` (settings now refuses to start if one is test and the other live, and strips stray whitespace).
2. Render (API **and** worker): set `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY` to the live pair; make sure `ALLOW_MOCK_UPGRADE` is unset.
3. Dashboard > Settings > API Keys & Webhooks (LIVE): webhook URL = `https://vendoriq-api.onrender.com/api/billing/paystack-webhook/` (test and live have SEPARATE webhook URLs) and your transfer-webhook URL for referral payouts.
4. Check the live prices in Django admin (plan prices), not the seed values.
5. **Referral payouts send real money**: with a live key `attempt_payout` makes real Paystack Transfers from your balance to referrers who saved payout details. Fund/enable Transfers deliberately, or keep referrals disabled in admin until you are ready.
6. Test with Paystack TEST keys first, end to end (checkout popup, verify call, webhook with the tab closed, refund). Then one real small live payment and refund it.
7. Known uncertainty (untested here): `UpgradeModal.jsx` opens the popup with `PaystackPop.setup({key, email, amount, ref, ...})` using the SAME reference the server already initialized. Paystack's current docs prefer completing a server-initialized transaction via its `access_code`. If the popup ever shows "Duplicate Transaction Reference", pass `access_code: data.accessCode` instead of `ref/amount`.
