# What changed, and what you still need to do

## 1. Admin crash when clicking a user from "Recent activity"
**Root cause:** `apps/authentication/admin.py` → `LoginEventInline` sliced its
queryset (`[:25]`) before Django's inline formset tried to `.filter(user=...)`
on it. Django refuses to filter an already-sliced queryset, so opening any
user's admin page raised a 500. Fixed by capping via `max_num = 25` instead
(which slices safely, *after* filtering) - also fixes a second bug where the
old `max_num = 0` was hiding all login history even when it didn't crash.

**Nothing for you to do** - this is a pure code fix.

## 2. Which AI model is used / AI provider now configurable from admin
You're currently on Groq's `openai/gpt-oss-120b` (via `GROQ_API_KEY` /
`GROQ_MODEL`), not actual OpenAI.

Added a new **AI provider & model** page under the AI section of Django
Admin (`apps/ai/models.py` → `AISettings`). From there you can:
- switch provider (Groq / OpenAI / any custom OpenAI-compatible endpoint)
- change the model string
- optionally override the API key for a quick test, without touching env vars

Changes take effect on the very next chat request - no redeploy. Falls back
to your existing `GROQ_API_KEY`/`GROQ_MODEL` env vars until you first visit
that page.

**To do:** run `python manage.py migrate` (new migration
`apps/ai/migrations/0002_aisettings.py`).

## 3. "AI usage" admin link not working
It was a raw anchor link (`/admin/#ai-usage`) that only worked when you were
already on the dashboard. Fixed the link, and added the new AI provider page
above as a proper nav item too.

## 4. "External prompt" - native browser confirm() popups
Replaced all 5 remaining `confirm(...)` calls with your existing in-app
`ConfirmDialog` component (it was already built, just unused in these
spots): `AIPage`, `StoresPage`, `ProductsPage`, `ExpensesPage`, `StaffPage`.

## 5. Paystack test payments
Implemented for real:
- Backend: `PaystackInitializeView` + `PaystackVerifyView`
  (`apps/billing/views.py`), wired into `apps/billing/urls.py`. Uses
  Paystack's actual REST API (`/transaction/initialize`,
  `/transaction/verify/:reference`) - server-side verification before
  activating Pro, never trusting the frontend alone.
- Frontend: `UpgradeModal.jsx` now opens Paystack's real inline test-mode
  popup when configured, and falls back to the old no-payment mock flow
  (`UpgradeView`) when it isn't - so local dev without keys still works.

**To do (required to actually test payments):**
1. Get **test** keys from https://dashboard.paystack.com/#/settings/developer
2. Backend `.env`: set `PAYSTACK_SECRET_KEY=sk_test_...` and
   `PAYSTACK_PUBLIC_KEY=pk_test_...`
3. Frontend `.env`: set `VITE_PAYSTACK_PUBLIC_KEY=pk_test_...` (same public key)
4. Use Paystack's test card `4084 0840 8408 4081`, any future expiry/CVV, to
   simulate a successful payment.

## 6. AI assistant chat not persisting / disappearing on refresh
The save (`ChatView`) and load (`ChatHistoryView` + `AIPage.jsx`'s
fetch-on-mount) code was actually correct. The real bug: the frontend
silently swallowed **any** error while loading history - so a genuine
backend error looked exactly like "my chat got deleted." Fixed to only stay
silent on a real "no history yet" (404) and show a toast for anything else.

**To do:** if you still see this after deploying, the toast will now tell
you it's a load failure (not silent data loss) - most likely cause is that
migration for the `ai` app hasn't been applied on your deployed database yet.
Check with `python manage.py showmigrations ai`.

## 7. Logo added throughout
Generated a full icon set from your uploaded logo (16/32/180/192/512px, plus
maskable variants) and placed it:
- Frontend favicons + PWA icons (`vendoriq-frontend/public/icons/`) - this
  also fixed a **pre-existing bug**: `manifest.json` pointed at
  `icon-192.png`/`icon-512.png` files that didn't actually exist yet (PWA
  "Add to Home Screen" install icon was silently broken), and the
  apple-touch-icon pointed at an SVG (unsupported by iOS).
- Sidebar header + mobile header (`AppLayout.jsx`)
- Login, register, and welcome pages
- Invoice email (`invoices/invoice_email.html`) - requires `FRONTEND_URL` set
  in the backend `.env` (falls back to your first `CORS_ALLOWED_ORIGINS`
  entry if left blank) so the logo has a real, absolute URL to be fetched
  from - emails can't use relative paths.
- Django Admin site logo/icon (`UNFOLD` settings + new
  `static/branding/logo.png`)

**To do:** run `python manage.py collectstatic` before deploying so the admin
logo is picked up in production, and optionally set `FRONTEND_URL` in
your backend `.env`.

## Before you go live - a short checklist
- [ ] `python manage.py migrate` (new AISettings table)
- [ ] `python manage.py collectstatic` (admin logo)
- [ ] Set `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY` (backend) and
      `VITE_PAYSTACK_PUBLIC_KEY` (frontend) - test keys first, live keys only
      once you're ready to accept real money
- [ ] Set `FRONTEND_URL` (backend) so invoice emails show the logo
- [ ] Visit Django Admin > AI > AI provider & model once, to confirm it's
      picked up your Groq (or OpenAI) key correctly
- [ ] Test the AI assistant, send a message, refresh the page, confirm the
      conversation is still there
- [ ] Do one full test purchase with Paystack's test card end-to-end

---

## 8. Legal pages, accessibility, and compliance (round 2)

**Not legal advice.** The policy pages below are a solid, codebase-accurate
first draft - they describe what the app actually does, not generic
boilerplate - but they have not been reviewed by a lawyer, and the
liability/governing-law clauses in particular should be reviewed by one
before you rely on them commercially.

### What was added
- **`/legal/privacy`, `/legal/terms`, `/legal/cookies`, `/legal/refunds`** -
  four new pages (`src/pages/legal/`), linked from the Welcome page, the
  Profile page, the signup form, and the Paystack upgrade flow.
- **`src/lib/businessInfo.js`** - single place to fill in your real business
  name, CAC number, address, and contact details. Every legal page and the
  footer pulls from this one file. **This still has placeholder values in
  it (`[YOUR REGISTERED BUSINESS NAME]` etc.) - the pages will look
  unfinished/untrustworthy until you fill these in.**
- **Cookie consent - do you need it?** Checked directly: the app sets no
  cookies of its own and only uses localStorage for strictly-necessary
  session/preference data (login token, theme, a couple of display
  toggles). No ads, no analytics/tracking cookies. Under most cookie-consent
  frameworks (including the EU's), strictly-necessary storage is exempt
  from requiring a consent gate - so a blocking "Accept/Reject" banner
  isn't legally required here. Added a lightweight, dismissible **disclosure
  notice** instead (`CookieNotice.jsx`) rather than a hard wall, since
  gating basic app use behind a click for something that needs no consent
  would just be friction. If you ever add real tracking/ads, upgrade this
  to a proper consent choice at that time.
- **Signup consent checkbox** - RegisterPage now requires agreeing to the
  Terms & Privacy Policy before the account can be created.
- **Payment consent line** - UpgradeModal now shows a Terms/Refund Policy
  link right above the Paystack button.
- **Fake reviews / unsupported claims** - checked the whole app; there's no
  testimonials section and no "trusted by X businesses"-style marketing
  copy anywhere to begin with, so nothing needed removing here.
- **Copyright on images** - checked; the only raster images are icons
  generated from your own uploaded logo, and the Welcome-page graphic is
  hand-coded SVG. No stock/third-party imagery found.
- **Third-party embeds inventory** (for the Privacy/Cookie policies above):
  Google Fonts, Paystack's checkout script, Google Sign-In's script, and
  optional Sentry (off by default, no PII sent). No ad trackers, no Google
  Analytics/Facebook Pixel found anywhere.
- **Data minimization** - checked what's actually collected at signup:
  name, email, optional phone, password. Nothing excessive - confirmed
  clean, no changes needed here.
- **Business details footer** - `BusinessFooter.jsx`, shown on the Welcome
  and Profile pages, pulls from `businessInfo.js` (see above - needs your
  real details filled in).

### Accessibility fixes (verified, not just eyeballed)
- **Color contrast** - computed actual WCAG contrast ratios for the color
  system (not guessed). Found and fixed two real AA failures: `text-slate-dim`
  was ~2.5:1 in light mode / ~3.1:1 in dark mode against its usual
  backgrounds (needs 4.5:1) - used on 140+ elements app-wide (timestamps,
  hints, nav labels) - and dark-mode primary buttons (white text on green)
  were 3.4:1. Both fixed at the CSS-variable/component level so the fix
  applies everywhere at once; math is in the code comments
  (`src/index.css`).
- **Keyboard access** - a clickable store card was missing Space-key
  support (only Enter worked) - fixed. Both `ConfirmDialog` components and
  `UpgradeModal` now close on Escape, move focus into the dialog on open,
  and carry proper `role`/`aria-modal` attributes for screen readers.
- **Clear button labels** - found and labeled 9 icon-only buttons that had
  no accessible name at all (theme toggle, show/hide profit and stock-value
  eyes, barcode scan buttons, add-new buttons, password show/hide toggles)
  - all now have `aria-label`.
- **Form labels** - every `<label>`/`<input>` pair app-wide (Login,
  Register, Stores, Products, Sales, Expenses, Staff, Invoices - 25+ fields
  total) now uses `htmlFor`/`id` (previously visual only, not
  programmatically linked - screen readers couldn't reliably announce them,
  and clicking the label text didn't focus the input). One label was
  deliberately left as-is: ProductsPage's "Product photo" is a group
  heading for an upload widget, not a 1:1 field label, so it doesn't need
  `htmlFor`.
- **Alt text** - checked; every `<img>` in the app already has one.
- **Modal keyboard/focus handling** - the two remaining inline modals
  (SalesPage's "create invoice" modal, InvoicesPage's "send invoice" and
  "email prompt" modals) now close on Escape and carry proper
  `role="dialog"`/`aria-modal`/`aria-labelledby`, matching ConfirmDialog and
  UpgradeModal. Also found and labeled 2 more icon-only close (X) buttons
  and one unlabeled email input in the process.

### Risks flagged (not fixed - need your input or a professional's)
- **Business identity is still placeholder.** `businessInfo.js` has
  `[BRACKETED]` values - fill in your real CAC number (or state plainly if
  you're not yet incorporated), address, and support contact before this
  goes live. Publishing a privacy policy with a fake business identity is
  itself a risk, not just an oversight.
- **Applicable law.** Given the Naira pricing, Paystack, and FUNAAB
  context, I've written these pages around Nigeria's Data Protection Act
  2023 (NDPA) and general FCCPC consumer-protection expectations for the
  refund policy. If you'll have users outside Nigeria, GDPR (EU/UK) or
  CCPA (California) may also apply and would need their own review -
  they're only briefly gestured at here, not fully addressed.
- **No automated data-retention/deletion enforcement.** The Privacy Policy
  says login logs aren't kept indefinitely, but there's no actual scheduled
  job in the codebase that purges old `LoginEvent` rows or handles a "delete
  my account" request end-to-end. Worth building before you'd want to say
  that with full confidence to a regulator.
- **Data Protection Officer.** NDPA requires one past certain
  processing-volume thresholds - `businessInfo.js` has a placeholder for
  this; whether you're required to appoint one yet is a threshold question
  worth checking directly with counsel or the NDPC as you grow.

---

## 9. Referral program (round 3)

Recurring commission (capped at N months), automatic Paystack Transfer
payouts, referral applied via link OR typed code at signup - as decided in
the conversation that built this.

### What was built
- **New `apps/referrals` Django app**: `ReferralSettings` (admin-editable
  commission % and cap-months - Django Admin > Referrals), `Referral` (who
  referred whom, set once at signup and never re-attributed),
  `ReferralCommission` (one row per commission-eligible payment, with
  status PENDING/PROCESSING/PAID/FAILED and a visible failure reason),
  `PayoutAccount` (bank details, Paystack-verified, never saved from a
  free-typed name).
- **`User.referral_code`** - every user gets a unique, collision-safe
  outgoing code on creation. Kept deliberately distinct from the new
  write-only `referred_by_code` field used at signup (the INCOMING code
  someone typed) - these are opposite directions and almost shared one
  name, which would have been a confusing bug to debug later.
- **Commission trigger**: hooked into `apps/billing/views.py::_activate_pro`,
  firing only for real Paystack payments (never the mock/dev upgrade flow),
  and wrapped so a referral-side failure can never break the customer's
  own successful payment.
- **Paystack Transfers integration** (`apps/referrals/paystack.py`): bank
  list, account resolution (confirms a real name before anything is
  saved), transfer recipient creation, transfer initiation, and a
  **signature-verified webhook** (`/api/referrals/paystack-webhook/`) that
  catches the async success/failure confirmation - HMAC-SHA512 verified
  against `PAYSTACK_SECRET_KEY`, exactly as Paystack's own docs specify.
- **Frontend**: new `/referrals` page (code + shareable link with
  copy/share, earnings summary, bank account setup with live verification,
  referred-users list, commission activity log), linked from Profile.
  Registration page now accepts `?ref=CODE` in the URL or manual entry.
- **Django Admin**: Referral settings, Referrals, Commissions (with
  failure reasons), Payout accounts - all under a new "Referrals" sidebar
  section.

### Required setup before this can pay anyone automatically
1. **Register the webhook** in your Paystack dashboard: Settings >
   API Keys & Webhooks > Webhook URL ->
   `https://<your-backend-domain>/api/referrals/paystack-webhook/`
   (test mode and live mode each have their own webhook URL field - set
   both once you're ready for each).
2. **Enable Transfers** on your Paystack account - this is a separate
   approval from just accepting payments; contact Paystack support if it
   isn't already enabled.
3. **Ask Paystack support to disable per-transfer OTP** for
   API-initiated transfers. Without this, every transfer will sit stuck
   waiting for a one-time PIN no one is there to enter - `attempt_payout()`
   handles this gracefully (marks the commission PROCESSING with that
   exact reason visible in Admin) but cannot complete the payout for you.
   This is the single most important item for "automatic" to actually mean
   automatic.
4. **Keep real funds in your Paystack balance.** Transfers pay out of
   money you're actually holding there (from collected subscription
   payments), not something Paystack advances - if the balance is
   insufficient, transfers will fail with a clear reason in Admin, but
   referrers won't get paid until it's topped up.
5. Run `python manage.py migrate` (three new/changed migrations:
   `authentication/0002_user_referral_code`,
   `referrals/0001_initial`, plus `billing`/`ai` migrations from earlier
   rounds if not already applied).

### What I could not verify
No Django or npm installation was available in this environment, so
everything below was checked by careful manual review and static
syntax-checking (every backend `.py` file compiles; every frontend `.jsx`
file parses cleanly with esbuild) - **not by actually running the app**.
Before relying on this:
- Run `python manage.py makemigrations --check` to confirm nothing was missed.
- Do one real end-to-end test: sign up with a referral link, upgrade that
  account to Pro with a real (test-mode) Paystack payment, confirm a
  `ReferralCommission` row appears, add a payout bank account for the
  referrer, and confirm a transfer actually initiates.
- Test the webhook specifically - Paystack's dashboard has a "Send test
  webhook" feature for exactly this.

### Design decisions worth knowing about
- Commission is calculated per successful payment, not per calendar month
  - since this app's Pro plan doesn't yet auto-renew (each renewal is
  today's same manual "Upgrade"/pay flow), "recurring for N months" maps
  to "the referred user's first N successful payments," whichever cadence
  they actually pay on.
  - **`PayoutAccount` intentionally stores the Paystack-verified account
  name alongside the bank details** - never just what the user typed - so
  the admin log always shows exactly who a transfer was actually verified
  against, not just what was entered.
- Self-referral is blocked (a code can't refer its own owner).
- A referral is permanent once set at signup - changing your code later
  doesn't retroactively affect anyone already attributed to you.

---

## 10. Referral program on/off switch (round 4)

Added a master **Enabled** toggle to Django Admin > Referrals > Referral
settings - the first field on that page.

**What turning it off actually does:**
- Stops new referral attribution at signup (registration form and Google
  sign-up both check it - a `?ref=` link or typed code is silently ignored
  while off, and the Referral field on the signup form hides itself
  automatically via a new public `/api/referrals/status/` check).
- Stops new commissions from being created on Pro payments.
- **Does NOT stop already-earned commissions from being paid out.** Money
  already owed to a referrer keeps processing normally via the existing
  payout flow - turning the program off is not a way to stop paying people
  what they're already owed, by design (see the comments in
  `apps/referrals/services.py`).
- The `/referrals` page keeps working for people who already have
  earnings/history - it just shows a paused notice and disables the
  copy/share buttons for *new* referrals while off.

Takes effect immediately on save (same cache-invalidation pattern as every
other admin-editable setting in this app) - no redeploy, no restart.

New migration: `referrals/0002_referralsettings_enabled.py` - run
`python manage.py migrate`.

---

## 11. Logic-error audit (round 5)

Went back through the money-handling code specifically (referrals +
billing/Paystack), since that's where a subtle bug does the most real
damage. Found and fixed six genuine issues:

1. **Payment amount was never actually verified.** `PaystackVerifyView`'s
   own docstring claimed a client "can't claim a cheaper/forged
   transaction was paid" - but the code only checked that the transaction
   *succeeded*, never that the *amount* matched anything. Worse: the
   subscription price recorded (and the referral commission computed from
   it) was re-fetched from "today's live Pro price" at verify time, not
   locked to what was actually paid at checkout time - if an admin changed
   the price in that window, the recorded price (and commission) could
   silently diverge from the real payment. Fixed: `PaystackVerifyView` now
   reads the actual paid amount back from Paystack's own response and
   passes it through explicitly; `_activate_pro` records exactly that,
   never a re-fetched "current" price, for any real payment.
2. **Failed referral payouts could never be retried automatically.**
   `sweep_pending_payouts` (triggered when a referrer adds/updates their
   bank account) only looked at `PENDING` commissions, never `FAILED` ones
   - so a payout that failed even once (bad account details at the time,
   a transient error) was stuck forever with no automatic path back to
   paid, even after the referrer fixed the problem. Now retries both.
3. **A commission's old failure reason could survive a successful retry.**
   `attempt_payout` never cleared `failure_reason` on success/re-attempt,
   so a commission that failed once and later succeeded could still show
   its old, wrong failure message next to a "Paid" status in Admin. Now
   cleared on every attempt, only re-populated when there's an actual
   current problem.
4. **Payout account could silently save the wrong bank "name."** If the
   banks cache was cold (fresh deploy, or a direct API call skipping the
   dropdown), the account got saved with its raw bank CODE ("058") in
   place of the actual bank name, with no fetch attempted. Now shares the
   same fetch-on-miss logic as the bank list endpoint.
5. **Unvalidated bank code / account number reached a Paystack URL
   unescaped.** Both fields accepted arbitrary characters; added regex
   validation (digits only, account number exactly 10) so nothing but the
   expected shape ever reaches that request.
6. **A stale bank-resolution response could overwrite a newer one.**
   Fast typing or pasting a different account number in the Referrals
   page's payout form had no protection against an older, slower request
   finishing after a newer one and showing the wrong verified name. This
   never affected what actually got saved (the backend independently
   re-verifies at save time), but it could show a misleading name on
   screen - fixed with a standard stale-response guard.

Also caught and fixed one smaller correctness gap: a Paystack webhook for
an unusual (theoretically duplicate) `transfer_code` could have thrown an
unhandled 500 instead of degrading gracefully - now defensive.

None of these were found by running the app (still no live DB/environment
available) - all found by re-reading the actual request/response flow
end-to-end and checking every assumption against what the code actually
does, not what its comments claimed it does. #1 in particular is worth a
real end-to-end test once you have a live environment: initialize a
Pro payment, change the Pro price in Admin before completing checkout,
finish the payment, and confirm the recorded price matches what was
actually charged, not the new price.

---

## 12. Security audit - "how would a hacker get in" (round 6)

Went through the project the way an attacker actually would: read the
auth flow, the admin surface, the tenant-isolation pattern, and the deploy
config, looking for the gap rather than assuming the comments were true.
Ranked by what I'd try first.

### 1. CRITICAL (if deployed outside the documented path): forgeable auth tokens
`SECRET_KEY` defaults to a hardcoded string sitting in plain text in
`settings.py` if the env var isn't set. `SIMPLE_JWT` has no separate
`SIGNING_KEY`, so simplejwt signs every access/refresh token with that
same value by default - anyone who reads that string (it's right there in
the source, and now in every export of this codebase) could forge a valid
JWT for **any** user_id, staff/superuser included, no password needed.

**The good news:** `render.yaml` already sets `SECRET_KEY: generateValue: true`
and `DEBUG: "False"` for both services - if you deploy exactly via that
blueprint, this was never actually exploitable. **The gap:** nothing at the
code level enforced that on any OTHER deploy path (a quick Railway/Fly.io
test, a raw VPS, a teammate spinning up their own copy) - which is exactly
how real breaches happen, someone deploys once outside the "official" path
and never notices.

**Fixed:** `settings.py` now raises `ImproperlyConfigured` at startup if
`DEBUG=False` and `SECRET_KEY` is still the placeholder - fails loudly
instead of silently serving traffic with a forgeable signing key, on any
deploy path. `DEBUG=True` (local dev) is exempt.

### 2. HIGH: the admin panel had zero brute-force protection
The customer-facing login (`LoginView`) has a well-built, temporary,
email-scoped lockout. Django Admin's login form - at the default,
well-known `/admin/` path - had none of that, despite controlling the
highest-value data in the app: referral commission rates, payout account
details, AI provider keys, every user's PII. An attacker would go straight
for `/admin/login/` over the protected customer login every time.

**Fixed:** a custom admin login form (`apps/authentication/admin.py`)
reuses the exact same `LoginEvent`-based lockout the API login already
has, instead of inventing a second mechanism.

### 3. MEDIUM: an authorization footgun waiting for the next contributor
`get_store_or_404(store_id, user)` accepted a `user` argument and silently
**ignored it** - actual access control lived entirely in a separate
`require_store_access()` call. Every current call site correctly calls
both (verified by reading each one), so this was not live-exploitable
today - but the signature actively invited a future "just pass `user` in,
looks like it's checked" mistake, which would ship a real IDOR with
nothing to catch it. Fixed: dropped the unused parameter so the function
can't be mistaken for doing authorization; updated all 3 call sites.

### 4. LOW: CORS trusts the entire public `*.vercel.app` namespace
`CORS_ALLOWED_ORIGIN_REGEXES` matches any `*.vercel.app` origin (to allow
preview deployments), which technically means anyone's free Vercel app
passes this CORS check too. Low real impact today specifically because
auth tokens live in localStorage, not cookies - another origin's JS can't
read that regardless of CORS. Documented the reasoning and the condition
under which it would stop being safe (cookie-based auth, or anything
sensitive touching a shared-domain cookie) directly in `settings.py`, and
noted `CORS_ALLOW_VERCEL_PREVIEWS=False` as the tightening knob once
preview URLs aren't actively needed.

### What I checked and found solid (no changes needed)
- Product photo upload: proper size limit + PIL-backed image validation,
  not just an extension check.
- Store/tenant isolation pattern (`StoreScopedAPIView`): enforced in DRF's
  `initial()` hook before any handler runs, not by convention.
- The Paystack transfer webhook: real HMAC-SHA512 signature verification,
  not just trusting the payload.
- The customer-facing login lockout itself: correctly temporary and
  email-scoped (not IP-scoped, not permanent - matches OWASP guidance
  against turning a lockout into its own DoS vector).

Same caveat as every round: no live environment to actually attempt any of
this against - all of the above was found and fixed by reading the real
request/response flow end-to-end, not by running an actual attack.
