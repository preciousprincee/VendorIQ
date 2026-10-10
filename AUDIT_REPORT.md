# VendorIQ - audit & fix report

Scope: `vendoriq-django` (all apps, settings, deploy config) and the parts of
`vendoriq-frontend` that interact with the fixes.

**Verification status.** The sandbox had no network, so Django/DRF could not be
installed and **the test suite was not run**. What was done: every Python file
compiles, an AST pass found no undefined names in any changed file, and the
migration was checked by hand against the model. Please run:

    pytest
    python manage.py makemigrations --check   # see "Known leftovers" (index names)

## Fixed - critical
| # | Problem | Fix |
|---|---------|-----|
| 1 | **Pay NGN 50, get a year of Pro.** Paystack's popup is configured in the browser; `verify` and the webhook trusted the metadata (cycle, user) and never compared the amount paid with any price. | New `CheckoutSession` (migration `0008`) records buyer, cycle, price at initialize. Verify + webhook use the session, refuse under-payment/other currency, and ignore charges we never started. |
| 2 | **Anyone could activate Pro with any successful reference** (verify never checked ownership). | Reference must belong to the requesting user's session. |
| 3 | **Double referral payout.** A timeout/5xx on the transfer call was recorded as FAILED, and the next sweep paid again under a fresh reference. | Ambiguous outcomes stay PROCESSING (never auto-retried) with the reference recorded; transfer webhook can match on reference. |
| 4 | **Multi-item sale lost stock.** A failure on item N committed the deductions for items 1..N-1 with no sale recorded (returning a Response inside `atomic()` commits). | Rejections now raise inside the transaction so everything rolls back. |
| 5 | **Trial overwrote paid Pro.** `start_trial` on a paying account replaced the period end/cycle; the customer fell to Free after 30 days. | Refuses accounts with Pro; row locked against double-tap. |

## Fixed - security
- `DEBUG` defaulted to **True** when unset; now False.
- Password change did not invalidate tokens (7-day JWTs). Tokens now carry a password fingerprint; change-password returns a fresh token.
- `X-Forwarded-For` was client-controlled: rate limits and recorded login IPs were spoofable (`NUM_PROXIES` + right-most parsing).
- Emails were case-sensitive: `Bob@x.com` and `bob@x.com` could both register (second free trial). Register/login are now case-insensitive.
- Invoice email: any staff member could send to any address with no validation or limit -> validated + throttled (`invoice_send`). AI chat throttled (`ai_chat`).
- Cashiers could read cost/profit (per product, per sale line, sale total) and change prices. Hidden / blocked server-side; form updated.
- Raw exception text was returned to clients on sale failure; the Paystack reference was interpolated unvalidated into a URL carrying the secret key; bank-resolve params were not URL-encoded.
- `CORS_ALLOW_CREDENTIALS` disabled (auth is a Bearer header).
- Deactivated Google accounts could get a token at sign-in.
- CSV export: store name could break/500 the `Content-Disposition` header.
- Webhooks were subject to the 30/min anon throttle (would 429 Paystack); charge webhook returned 200 on internal errors so Paystack never retried a paid customer.
- A late transfer webhook could flip a REVERSED (refunded) commission back to PAID/FAILED - and FAILED would then be paid out by the sweep.

## Fixed - bugs / crashes
- Trend chart dropped today's sales for the first hour after Lagos midnight (UTC vs local date loop).
- Previous-month comparison overflowed into the current month on the 29th-31st.
- `?days=abc`, negative or huge `days`; bad `?start=`/`?end=` dates -> 500s, now 400s.
- Invoice creation: missing customer name (NOT NULL), NaN/Infinity/negative price, non-object items, no atomicity, unvalidated email.
- AI chat: non-string message / non-UUID storeId -> 500; null model reply -> 500; history returned the OLDEST 50 messages instead of the newest.
- Duplicate barcodes -> `MultipleObjectsReturned` at the till; restock race and `true` accepted as quantity 1.
- Duplicate `LOGGING` block silently replaced the first (lost `django.security`).
- Mock (demo) upgrades inflated MRR/ARR; `SubscriptionPurchase.referral` was never set.
- Frontend: a failed login reloaded the page and wiped the error toast (401 interceptor).
- `render.yaml`: worker had no `FRONTEND_URL` (broken logo in invoice emails); Paystack keys, `NUM_PROXIES` were missing.

## Tests added
`apps/billing/test_payment_security.py`, `apps/authentication/test_security.py`, `apps/sales/test_atomicity.py`.

## Round 2 - leftovers closed + new features

### Leftovers from round 1
| Leftover | Now |
|----------|-----|
| Trial abuse (phone optional/unverified) | Phone is **required** at signup and must be verified by SMS (6-digit code: hashed at rest, 10 min expiry, 5 guesses, resend cooldown, hourly + per-number daily caps). Free trial **and** checkout are refused (403 `verification_required`) until email + phone are verified. An unverified number can be claimed by its real owner, so nobody can squat a stranger's number. |
| No email verification | Same flow by email code. Google sign-in counts as email-verified. Existing accounts are asked to verify on next login (Google-only accounts are auto-marked). |
| 7-day tokens, no refresh | 1-hour access token + 30-day refresh token; the frontend refreshes silently and replays the request. Refresh dies on password change / deactivation. |
| Staff add revealed registered emails | Case-insensitive, non-string input rejected, and throttled (20/hour). (The 404 wording is kept - a manager needs to know the person must register first - but probing is rate-limited.) |
| Prompt injection via product names | Names/store name are flattened to one short line before entering the AI prompt; prompt tells the model the data section is untrusted. |
| Web/worker `SECRET_KEY` mismatch | `render.yaml` now asks for one shared value on both. |

### Requested changes
- **/stores:** removed the "Profile & referrals" text link (the round profile icon stays).
- **Top navbar:** theme icon removed; only the notification bell remains (theme is still in the side menu and Settings).
- **Notifications (new `apps/notifications`):** one bell for everyone. Unread badge clears when the bell is opened (and stays cleared after refresh / other devices). Includes per-user reminders (trial ending at 5/2/1 days; plan expiring at 7/3/1 days; plan expired), admin announcements, and the existing stock/invoice alerts for owners/managers.
- **Admin -> Notifications -> "Send notification to all users":** title + message (+ optional in-app link, expiry). Shows in every user's bell immediately; untick *Is active* to withdraw.
- **Settings routing:** Privacy/Terms/Refund "Back" returns to where you came from (was hard-wired to /welcome -> /stores).
- **Profile/Settings/Referrals from /stores:** no hamburger, sidebar or bottom tabs; a store icon sits in the top bar (replacing the theme icon) to go back.
- **Settings -> Install app:** works with Chrome/Edge's install prompt; shows manual steps on iOS/other browsers; shows "installed" once installed.
- **Scanner blank screen:** root cause was the camera being started before the `<video>` element existed on the page (the stream went to a hidden element), plus a removed `reset()` call so the camera was never released. Replaced the three copies with one `BarcodeScanner` component (also: back camera preferred, product-barcode formats only, errors shown on screen, same-barcode debounce on the sales screen).
- **Deleted AI messages stay visible to admins:** "clear chat" is now a soft delete (`deleted_at`); admin conversation view marks them "deleted by user".
- **Admin plan price in naira:** the form takes/shows Naira and converts to kobo on save.
- **Paystack checkout 503 and empty bank list:** both are caused by `PAYSTACK_SECRET_KEY` / `PAYSTACK_PUBLIC_KEY` being empty on the server (they were absent from your `.env`). Fill them in and restart - see below. Also fixed separately: the bank list only ever returned Paystack's first 50 banks; it now pages through all of them, and the referral page shows the reason + a retry button instead of an empty dropdown.

## Round 3 - second-look review (bugs found in my own earlier work + one old one)
| Bug | Impact | Fix |
|-----|--------|-----|
| **Service worker served `index.html` cache-first from a never-bumped cache** (pre-existing) | Installed/returning users would keep the OLD app forever - none of this release (scanner fix, verification screen, notifications) would ever reach them | Pages are now network-first (cache only as the offline fallback); cache renamed `vendoriq-v2` so existing installs update |
| New users saw announcements sent before they signed up, all counted unread | Fresh account opened with a stack of stale "unread" items | Announcements only reach users who existed when they were sent |
| A newly overdue invoice could never light the unread badge | Alert was timestamped with the invoice's creation date (always >14 days old), so it always looked "already seen" | Timestamped when it *became* overdue |
| Resend cooldown also blocked correcting a mistyped phone number | Had to wait 60 s after a typo | Cooldown only applies to the same number; hourly + per-number caps still bound abuse |
| Two simultaneous multi-item sales could deadlock | Postgres aborts one customer's sale | Products are locked in a consistent (id) order |
| Verify page fired a toast during render | React "update during render" warning; possible double toast | Moved to an effect |

Also re-checked and found sound: every intra-project import resolves, all model attributes/URLs/fixtures/migration dependencies the new code references exist, every throttle scope has a configured rate, the auth-context rewrite still exports everything the pages use (with original signatures), the plan-price admin form matches `PlanPrice.save()`, and soft-deleted AI messages are filtered in every user-facing query while admin stats still count them.

## Round 4 - Full POS + offline mode + real "Pro" features

### What the Pro "Cloud storage" claim actually was
`cloud_backup` and `customer_management` (and `detailed_reports`, `automated_summaries`) were **only labels** in the Pro plan list - nothing in the code enforced or implemented them. All shop data already lives in the cloud database (Postgres) on **every** plan; that is how the app works. This round makes two of the labels true: **Customer management & credit sales** (below) and **Cloud backup = a full-store data download** (Settings -> Download a full backup; owner only; JSON of products, customers, sales with items/payments/returns, expenses, invoices, shifts). The plan text was reworded to say exactly that. `detailed_reports` / `automated_summaries` are still labels - decide whether to build them or drop the wording.

### POS features added
| Area | What it does |
|---|---|
| Payments | Cash / Transfer / Card, **split payments**, cash **change** calculation, quick-cash buttons. Old clients that send no payment info still work (paid in full, cash). |
| Discounts | % or flat amount per sale. Cashiers are capped (`CASHIER_MAX_DISCOUNT_PERCENT`, default 10); owners/managers are not. |
| Credit sales (Pro) | Choose a customer, take a part-payment or none; the rest becomes their debt. |
| Customers (Pro) | Add/search customers, running balance, statement of purchases and payments, **receive debt payments** (applied to oldest sale first). |
| Receipts | Printable 80mm-friendly receipt (works offline), WhatsApp share, reprint from the sales list. Receipt number matches before and after sync. |
| Returns/refunds | Partial or full, per item, discount shared pro-rata, restock optional, refund method; goods from an unpaid credit sale just reduce the debt. Owner/manager only. |
| Till / shifts | Open with a float, close with a cash count -> expected vs counted vs difference; per-cashier; shift report and an **end-of-day summary** (by payment method, discounts, returns, credit, debt collected). |
| Owner review queue | Anything the server could only notice after the goods left (stock ran out, price changed, discount over a cashier's limit) is recorded **and flagged** - shows in Sales -> "Needs review" and in the notification bell. |

All reports keep working with no changes because `total_amount`/`total_profit` are now the *net* figures (after discount and returns).

### Offline mode - how it works
- The till downloads a **catalog** (products without cost prices, customers + balances, open shift) and keeps it on the device (IndexedDB). It refreshes whenever online.
- A sale is rung up against that local copy. **Online:** sent immediately through the normal strict endpoint (the server can refuse "not enough stock" on the spot). **Offline or the request fails:** saved in an **outbox** on the device, receipt printed straight away, local stock lowered so it can't be oversold.
- When the connection returns (and every 30 s, on app focus, on the browser's "online" event) the outbox is sent in batches. Every operation carries a client id the server de-duplicates on, so retries can never double-record a sale - even when the reply was lost.
- A banner always says what is happening ("Offline - 3 sales saved...", "Syncing...", "2 items need attention"). Nothing is silently dropped: rejected items stay in a list with the server's reason until retried or discarded.
- Offline sales keep the time they happened (within the last 7 days, never in the future; device-clock errors are corrected using the server's clock).
- Works offline: ringing up sales, barcode scanning (once the scanner has been opened online once), receipts, customer list/balances, receiving debt payments. **Needs internet:** adding products/customers, returns, opening/closing the till, reports, dashboard, AI.
- Different cashiers on one device never send each other's queued sales.

### Verification (honest)
- **Executed here:** the real offline queue/sync/catalog code against a scripted fake server (24 checks incl. mid-batch network loss, duplicates, rejections, per-user isolation); the till's money maths vs the server's Python functions on 600 random sales (0 mismatches); every frontend file (65) parsed and import-resolved with esbuild (this also caught and fixed a duplicate-import build error in my own change).
- **Not executed (no Django/network here):** the new backend suite `apps/sales/test_pos.py` (hand-computed expectations for payments, change, credit, discounts, returns, debt allocation, shifts, sync edge cases, backup, customers) and the migrations. Please run `pytest`, `python manage.py migrate`, `python manage.py makemigrations --check`, `npm run build`.

### Decisions / limits to know
- Returns reduce the **original sale's** figures (so a return next month lowers that earlier month's revenue) - simplest way to keep every report correct; say if you prefer returns to be booked on the day they happen.
- Offline price: the price the till showed is honoured and flagged if it differs from the current price - a cashier could in theory enter a lower price on a tampered client; owners see the flag.
- Printing uses the browser's print dialog (works with any installed thermal printer driver). Direct Bluetooth/USB ESC-POS printing is not included.
- Detailed Reports / Automated Summaries (Pro labels) remain unbuilt.

## Round 5 - recheck of the POS/offline work
| Bug | Impact | Fix |
|-----|--------|-----|
| **Service worker fabricated a "503 You are offline" reply for API calls** (pre-existing behaviour, but it broke the new offline mode) | A real network failure looked like a server error, so with wifi-but-no-internet the offline banner never showed, the offline sales view never appeared, and the app couldn't tell "no connection" from "server problem" | The worker no longer touches API requests; real network errors reach the app. Cache renamed `vendoriq-v4`. Verified by running the actual worker in a harness |
| Receipt printed at the till differed from the reprint of the same sale after sync ("Cash 500 / Change 200" vs "Cash 300 / Change 200") | Confusing for customers and staff | Reprints show cash handed over; verified identical to the till receipt (and split/exact cases unchanged) |
| Every sale waited up to 12 s for a live attempt even when the connection was already known to be down | Slow counter at the worst moment | When the last request showed we are offline, sales are queued immediately |
| First product download failing left the till on "Loading..." forever | Stuck screen | "Try again" button |
| Backup filename lost cross-origin | Always `vendoriq-backup.json` | `Content-Disposition` exposed through CORS |
| Non-object JSON body on shift / customer-payment endpoints | HTTP 500 | Treated as an empty body (-> a normal 400) |
| Earlier this round: cashier A's queued sales could be sent under cashier B's login | Wrong attribution on shared devices | Fixed; test fails on the old code |

Re-verified this pass: models vs hand-written migrations match field-for-field; every cross-module import resolves; no existing test asserts anything I changed; offline suite now 25 checks (all pass); frontend 65 files parse and resolve. **Still not executed:** the new Django tests and migrations (no Django/network in the sandbox).

Known limitations (not changed): an invoice created from a *discounted* sale lists items at full price but totals the discounted amount (the invoice model has no discount line); a catalog refresh that lands in the same instant as an offline sale can briefly show stale stock until the next refresh (self-corrects).

## Round 6 - deletion approvals, photo storage, brand icon
- **Brand icon:** `/stores` showed a generic bar-chart placeholder next to "VendorIQ" while every other screen uses the real logo. Fixed (also added the logo to the verification screen).
- **Cashier product deletion with approval.** Before: the trash button was shown to cashiers but the server always answered 403. Now a cashier taps it, must write a remark (5-300 characters), and the request goes to the owner and every manager through the notification bell. The first to approve or decline settles it; approval deletes the product, a decline keeps it, and the cashier is told either way (with the approver's note). The other approvers' notifications disappear once it is decided. A cashier can cancel their own pending request. Every request is kept as an audit record (admin: Products -> Product deletion requests). A product that already has sales or invoices cannot be deleted (the database protects that history); the cashier is told immediately instead of sending managers an impossible request, and an approval blocked by a sale made after the request leaves the request pending so it can be declined with a reason.
- **Product photos:** one photo per product (already a single field), now with: 1 MB upload cap (`PRODUCT_PHOTO_MAX_UPLOAD_BYTES`), only JPEG/PNG/WebP, a pixel-count guard against decompression bombs, automatic re-encode to a WebP of at most 800 px (typically 20-100 KB) which also **strips GPS/EXIF metadata**, random file names, and automatic deletion of the old file when a photo is replaced or the product is deleted. The web app shrinks phone photos in the browser first so honest users are never bounced. **Storage moved off local disk** to any S3-compatible bucket (Supabase Storage, S3, R2) via django-storages - set the `MEDIA_S3_*` variables (see `.env.example`); without them production prints a warning at build/check time.
- **System design PDF** updated (v1.1): object-storage box, deletion-request flow and audit table, role matrix, new section 10.4 (HttpOnly-cookie sessions with offline use), risks (photo item resolved pending configuration), and the document date corrected.

**Verified by execution:** the photo module on real images (large file refused; 1200x900 photo stored as ~100 KB WebP; GPS EXIF removed; transparent PNG flattened to white; GIF/BMP/garbage refused; a 36-megapixel solid-colour file refused before decoding; rotated phone photo stored upright). **Not executed:** the new Django tests (`apps/products/test_deletion_and_photos.py`) and migrations (`products 0003`, `notifications 0002`), and the S3 storage against a real bucket (no Django or network here).

## Round 7 - HttpOnly-cookie sessions (review + fixes), consent-gated analytics
**Cookie sessions (built last round, reviewed now).** The refresh token is no longer in any JSON body; it lives in the `viq_refresh` HttpOnly/Secure/SameSite=Lax cookie scoped to `/api/auth/`, the access token lives only in page memory, and refresh/logout require the `X-Requested-With` header. Re-read end to end; two real defects found and fixed:
- **Refresh-vs-sign-out race.** A token refresh already in flight when the user signed out (or another account signed in) would finish afterwards and store the OLD user's access token in memory - resurrecting a signed-out session, or giving the new account the old account's token. The session now carries an "identity epoch" (`lib/session.js`): sign-in and sign-out bump it, a refresh that started under an older epoch is discarded and never joined by new callers, and the 401 handler no longer wipes a *new* user's session when the old request fails (`lib/api.js`, `AuthContext.jsx`, change-password flow).
- **Wrong legal copy.** The cookie notice and Cookie Policy still said the app "sets no cookies". It now sets one (strictly necessary) sign-in cookie; both pages say so, and a stale CORS comment that claimed auth is "never a cookie" was corrected.

**Analytics (PostHog) - browser + server, always on, no opt-in (product decision).**
- Browser (`src/lib/analytics.js`): off unless `VITE_POSTHOG_KEY` is set; then runs in the background for every visitor. posthog-js loads lazily (own chunk); no autocapture, no session recording, no cookies (localStorage), query strings/fragments stripped from URLs (referral codes), personal-looking property names stripped from every event; identified by user id only (+ role, plan); `reset()` on sign-out; a different user on the same device is never merged. If the library can't load (offline) events are dropped and the download is retried at most once a minute. Events: `login`, `checkout_started`, `sale_completed` (value, item count, payment methods, offline flag), `sale_synced` (queued sales only), `offline_mode_entered`, `product_created`, the two deletion-request events, `feature_gate_hit`, `install_prompt_accepted`, `$pageview`.
- Server (`vendoriq/analytics.py`, `posthog` package): off unless `POSTHOG_API_KEY` is set. Sent from a background thread and only after the DB transaction commits; every failure is swallowed, so analytics cannot break a request. Events: `sign_up` (email, and Google - de-duplicated so a double-click counts once), `email_verified`, `phone_verified`, `trial_started`, `subscription_purchased`. The purchase event is emitted inside `create_subscription_purchase`, the single idempotent path used by the browser verify call AND the Paystack webhook - so it is counted exactly once even when the customer closed the tab, and the dev-only mock upgrade is not counted. Server and browser use the same user id, so PostHog shows one person; to avoid double counting each of those five events is sent by the server only.
- `GoogleLoginView` returns `isNewAccount` so the browser can tell a repeat Google sign-in from a first one.
- **Legal:** because there is no opt-in, the consent banner, Settings switch and consent hook were removed, and the notice is now a plain disclosure. Privacy Policy (analytics section, PostHog as processor, legitimate-interest basis, how to object) and Cookie Policy were rewritten to say this truthfully. Collecting analytics without consent can conflict with GDPR/ePrivacy (EU/UK visitors) and the NDPA's consent and objection rules; the data is kept minimal on purpose (random id, no name/contact/customer/product data) but have a lawyer confirm before relying on it.

**Verified by execution:** browser analytics logic (identify/reset/identity switching, URL stripping, personal keys stripped, offline failure + backoff, unconfigured = no-op) and the session/refresh logic (7 scenarios including both race cases) against fakes; all 68 frontend files parse and every relative import / identifier resolves; backend files compile. **Not executed:** `pytest` (new: `test_server_analytics.py`, `test_google_new_account.py`; earlier: `test_cookie_sessions.py`), migrations, `pip install` (adds `posthog`), `npm install` (adds `posthog-js`), `npm run build`, anything against real PostHog or Vercel.

**Deploy-blocker found in the final sweep (fixed):** the `LoginEvent` model (login history and the brute-force lockout) had **no migration**, so a fresh database had no `login_events` table and every login/registration would have answered 500. Added `authentication/0005_loginevent.py`, which creates the table only if it is missing (safe if your database already has it) and pinned the two index names in `models.py` to match. Also re-read the sales/returns/shift money paths, the offline sync endpoint, store/staff permissions, customers, referral payouts and the Paystack transfer webhook: no further defects found. The index names were computed with Django's naming algorithm without running Django; if `makemigrations --check` still reports a rename for them, accept the generated rename.

## Set this up before it works end-to-end
1. **Paystack** (fixes the 503 and the bank list): put `PAYSTACK_SECRET_KEY` and `PAYSTACK_PUBLIC_KEY` (test pair while testing) in `.env` locally and in Render's environment, then restart. Register `<api>/api/billing/paystack-webhook/` (and your existing transfer webhook) in the Paystack dashboard.
2. **SMS**: create a Termii account, get an approved sender ID, set `TERMII_API_KEY` / `TERMII_SENDER_ID`. Locally, leave it empty - the code appears on the verify screen and in the server log (DEBUG only; in production without a key verification says "temporarily unavailable").
3. **Email**: verification codes use your existing SMTP settings (`EMAIL_*`); with none set in DEBUG they print to the console.
4. `python manage.py migrate` (new: `authentication 0004`, `billing 0008`, `ai 0003`, `notifications 0001`).
5. Render: set `FRONTEND_URL`, `NUM_PROXIES=2` (Vercel proxies `/api`, so two proxies sit in front; use 1 only if the browser calls Render directly), and the **same** `SECRET_KEY` on the API and the worker.

## Verification status
Sandbox has no network, so neither `pytest` nor `npm run build` could be run. Done instead: every Python file compiles, an undefined-name scan of all 120 backend files is clean, the frontend files were bracket-balance checked against the originals. New tests: `test_verification.py` (email/phone flow, lockout, cooldown, billing gates, refresh tokens), `notifications/tests.py`, plus earlier round-1 tests (existing registration tests were updated for the now-mandatory phone). Please run `pytest`, `python manage.py makemigrations --check`, and `npm run build`.

## Known leftovers / decisions for you
- Verification is enforced in the frontend for **everyone** (existing users too) and in the backend for trial + checkout. If you'd rather not interrupt existing paying customers, exempt them in `RequireAuth` (App.jsx) and keep the backend gate.
- Cashiers can still create products (and see them); they just can't see cost or change prices.
- User-deleted AI messages are hidden from the user but are also removed if the **user account or store itself** is deleted (cascade). Say if you want those retained too.
- `.env` (placeholders, `DEBUG=True`) is in the upload - keep it out of git.
- Older migrations may have index names that differ from Django's auto-names; if `makemigrations --check` complains, generate a rename migration instead of editing old ones.
