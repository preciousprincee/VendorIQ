# VendorIQ Django Backend

## Setup

### 1. Create and activate virtual environment
```bash
cd vendoriq-django
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
# Mac/Linux
cp .env.example .env

# Windows
copy .env.example .env
```
Fill in your actual values in `.env`, including a fresh `GROQ_API_KEY` from
https://console.groq.com/keys (required for the AI Assistant page to work).
Never commit your real `.env` file - it's already listed in `.gitignore`.

### 4. Run migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Create an admin account (optional, for /admin/)
```bash
python manage.py createsuperuser
```

### 6. Start the server
```bash
python manage.py runserver
```

Server runs on http://localhost:8000

### 7. Background tasks (optional locally)
Invoice emails run as a background task via Celery. Locally, if `REDIS_URL`
is unset in your `.env`, `CELERY_TASK_ALWAYS_EAGER=True` kicks in
automatically (see `settings.py`) and tasks just run inline in the request -
**nothing extra to install or run to test this locally.**

If you do want to test the real async path (e.g. you've set `REDIS_URL` to a
local Redis), run a worker in a separate terminal:
```bash
celery -A vendoriq worker --loglevel=info
```

## API Endpoints

All same as before but base URL is now port 8000.

### Auth
```
POST   /api/auth/register/
POST   /api/auth/login/
GET    /api/auth/me/
```

### Stores
```
GET    /api/stores/
POST   /api/stores/
GET    /api/stores/{id}/
PATCH  /api/stores/{id}/
DELETE /api/stores/{id}/
```

### Products
```
GET    /api/stores/{id}/products/
POST   /api/stores/{id}/products/
GET    /api/stores/{id}/products/barcode/?barcode=xxx
GET    /api/stores/{id}/products/{id}/
PATCH  /api/stores/{id}/products/{id}/
PATCH  /api/stores/{id}/products/{id}/restock/
DELETE /api/stores/{id}/products/{id}/
```

### Sales
```
GET    /api/stores/{id}/sales/
POST   /api/stores/{id}/sales/
GET    /api/stores/{id}/sales/{id}/
```

### Invoices
```
GET    /api/stores/{id}/invoices/
POST   /api/stores/{id}/invoices/
GET    /api/stores/{id}/invoices/{id}/
PATCH  /api/stores/{id}/invoices/{id}/status/
POST   /api/stores/{id}/invoices/{id}/send/   - emails the invoice to the customer, marks it SENT
DELETE /api/stores/{id}/invoices/{id}/
```

### Staff
```
GET    /api/stores/{id}/staff/
POST   /api/stores/{id}/staff/
PATCH  /api/stores/{id}/staff/{id}/
DELETE /api/stores/{id}/staff/{id}/
```

### Insights
```
GET    /api/stores/{id}/insights/dashboard/       (owner/manager only)
GET    /api/stores/{id}/insights/trend/?days=30   (owner/manager only)
```

### Expenses & profitability
```
GET    /api/stores/{id}/expenses/                 (owner/manager only)
POST   /api/stores/{id}/expenses/                 (owner/manager only)
PATCH  /api/stores/{id}/expenses/{id}/            (owner/manager only)
DELETE /api/stores/{id}/expenses/{id}/             (owner/manager only)
GET    /api/stores/{id}/profitability/            (owner/manager only) - net profit after expenses
```

### AI
```
POST   /api/ai/chat/                              (owner/manager only)
```

## Deploying to production (Render + Supabase)

This is set up to deploy straight from `render.yaml` as a Render Blueprint.

### 1. Supabase (database)
1. Create a project at supabase.com.
2. Go to **Project Settings -> Database -> Connection pooling**.
3. Copy the **Transaction** mode connection string (port `6543`), not the direct
   connection (port `5432`). The pooler is built for many short-lived
   connections from an app server under load; the direct connection has a low
   hard limit on simultaneous connections and will run out fast with more than
   a couple of gunicorn workers.

### 2. Render (backend)
1. New -> Blueprint, point it at this repo (`render.yaml` is auto-detected).
   This provisions three services: the web API, a Celery worker (background
   tasks - currently just invoice emails), and Redis (shared cache + task
   broker for both).
2. Set these environment variables in the Render dashboard **on both the
   `vendoriq-api` and `vendoriq-celery-worker` services** (the worker needs
   its own copies since it also talks to the database and sends the actual
   emails):
   - `DATABASE_URL` - the Supabase pooler string from step 1
   - `GROQ_API_KEY`, and `EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` if you want the AI assistant and invoice emails to work
   `CORS_ALLOWED_ORIGINS` only needs setting on `vendoriq-api` (the worker doesn't serve HTTP):
   - `CORS_ALLOWED_ORIGINS` - your Vercel URL, e.g. `https://vendoriq.vercel.app`
3. Deploy. `render.yaml` handles `pip install`, migrations, `collectstatic`,
   and starts gunicorn with multiple worker processes and threads so one slow
   request (an AI call, an outbound email) doesn't block other users.
4. Bump the `plan` in `render.yaml` (Starter -> Standard/Pro) as real traffic
   grows - more CPU means you can safely raise `WEB_CONCURRENCY`.

### 3. Vercel (frontend)
1. Import the `vendoriq-frontend` folder as a Vercel project.
2. In Project Settings -> Environment Variables, set `VITE_API_URL` to your
   Render backend's URL with `/api` on the end, e.g.
   `https://vendoriq-api.onrender.com/api`. Without this, the deployed
   frontend has no way to reach the backend (they're on different domains).
3. Deploy. `vercel.json` already handles SPA routing.

### Scaling notes
- The Django views now aggregate in the database (`Sum`/`Count`) instead of
  loading full tables into Python - this was the main thing that would have
  degraded badly under concurrent dashboard/product-list traffic.
- API responses are rate-limited by default (`THROTTLE_RATE_ANON`/`_USER` env vars).
- **Caching**: `render.yaml` provisions a managed Redis instance and wires its
  `REDIS_URL` into the web service automatically, so this is live by default
  on Render - not just something you'd need to turn on by hand. The most
  expensive endpoints (`/insights/dashboard/`, `/insights/trend/`,
  `/profitability/`, `/notifications/`) are cached per-store for 45-300
  seconds (see `vendoriq/cache_utils.py`), and every write that changes a
  sale, expense, product, or invoice status immediately invalidates that
  store's cached figures - so nobody sees stale numbers after making a
  change, and everybody's dashboard doesn't recompute the same aggregation
  independently on every request. `django-redis` is configured with
  `IGNORE_EXCEPTIONS=True`: if Redis is ever unreachable, cache reads/writes
  silently no-op and the app falls back to querying Postgres directly -
  a cache outage degrades performance, it does not turn into a 500 for
  every user. Locally (no `REDIS_URL` set), it falls back to Django's
  in-memory cache automatically - nothing extra to run in dev.
  This also fixes throttle accuracy: DRF's rate limiting uses this same
  cache, so request counts are now correctly shared across every
  gunicorn worker/dyno instead of each process keeping its own count.
- **Want to actually test this instead of taking it on faith?**
  `python manage.py seed_demo_data` generates realistic dummy stores,
  products, sales, expenses, and invoices, and `loadtest/` has a Locust
  script that simulates many concurrent real users against those seeded
  accounts. See `loadtest/README.md`.
- Database migrations are committed to this repo under each app's
  `migrations/` folder. The Render build command just runs `migrate`
  against them, so production schema always matches what's in source
  control instead of being regenerated fresh on every deploy.

## Google sign-in setup

Email/password login works with zero configuration. Google sign-in is
additive - the button just doesn't appear on Login/Register until you do
this (it's driven entirely by whether `VITE_GOOGLE_CLIENT_ID` is set on the
frontend), so there's no rush and no risk in leaving it unconfigured.

1. Go to https://console.cloud.google.com/apis/credentials (create a new
   Google Cloud project first if you don't have one - it's free).
2. **Configure the consent screen** first if prompted (Credentials -> OAuth
   consent screen): External user type, fill in the required fields
   (app name, support email). Nothing here needs to be perfect for testing.
3. **Create credentials -> OAuth client ID -> Application type: Web application.**
4. **Authorized JavaScript origins** - add every origin the frontend runs on:
   - `http://localhost:5173` (local dev)
   - Your Vercel URL, e.g. `https://vendoriq.vercel.app`
5. **Authorized redirect URIs**: not required for this integration - it uses
   Google's client-side ID-token flow (the "Sign in with Google" button),
   not a server-side redirect, so you can leave this blank.
6. Save. You'll get a **Client ID** and **Client secret**.
7. Set them:
   - Backend `.env`: `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`
     (both - the backend verifies the token server-side)
   - Frontend `.env`: `VITE_GOOGLE_CLIENT_ID` (Client ID only - the secret
     never goes in frontend code, it's not safe to expose there)
   - In production, set the same on Render (both `vendoriq-api` and
     `vendoriq-celery-worker` don't need it, only `vendoriq-api` does) and
     on Vercel.
8. Restart both dev servers. The button should now appear.

**How it works, if you're curious**: this uses Google's client-side "Sign In
With Google" widget, which returns a signed ID token directly to the
browser - no OAuth redirect dance. The frontend POSTs that token to
`/api/auth/social/google/`, which verifies it with Google
(`apps/authentication/social_views.py`, via django-allauth), finds-or-creates
the matching `User`, and returns the exact same `{token, refresh, user}`
shape as the regular login endpoint - so nothing else in the app needs to
know or care which method someone signed in with.

A brand-new Google sign-up gets their `name` populated from their Google
profile automatically (`apps/authentication/adapters.py`) - this needed a
small custom adapter since this project's `User` model has a single `name`
field rather than Django's standard `first_name`/`last_name`, which is what
allauth assumes by default.

## Error monitoring (Sentry)

Off by default - `SENTRY_DSN` unset means it's a complete no-op, same
pattern as Redis/Celery/Google sign-in elsewhere in this project. Worth
turning on before real users touch the app, though: right now, an
unhandled error only surfaces if someone happens to be reading Render's
logs at the right moment.

1. Create a free account/project at https://sentry.io - **create two
   projects**, one Python/Django, one JavaScript/React (Sentry separates
   errors by platform).
2. Each project's Settings -> Client Keys (DSN) gives you a DSN URL.
3. Backend: set `SENTRY_DSN` in `.env` (and on both `vendoriq-api` and
   `vendoriq-celery-worker` in the Render dashboard for production - the
   worker needs it too, so a failed invoice-email background task gets
   reported, not just web request errors).
4. Frontend: set `VITE_SENTRY_DSN` in `.env` (and on Vercel for production).
5. Restart both dev servers. Trigger a real error to confirm it's wired up
   (e.g. temporarily `raise Exception('test')` in a view, or throw in a
   frontend event handler) - you should see it in the Sentry dashboard
   within a few seconds.

`SENTRY_SEND_PII` stays `False` unless you explicitly set it to `True` -
this app handles real names/emails/phone numbers, so request/user data
isn't sent to Sentry by default.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

Covers: registration/login, tenant isolation (a store's data is never
reachable by an unrelated user - the most important property of a
multi-tenant app), role permissions (owner/manager/cashier), staff
self-add prevention, sale recording + stock deduction + insufficient-stock
rejection, sale deletion permissions (cashiers can only delete their own),
and the dashboard's net-profit calculation.

This is a starting suite covering the highest-risk paths (auth, tenant
isolation, money-affecting logic), not full endpoint coverage - expenses,
invoices, staff role updates, and the AI assistant don't have tests yet.
Extend it the same way as new features are added: a `tests.py` per app,
`APIClient` + the fixtures in `conftest.py`.

**Honesty note:** this suite was written without a live Django install
available to run it against (no network access in the environment these
fixes were authored in), so while every model field, serializer field name,
and endpoint response shape was cross-checked against the actual source
files, it hasn't been executed end-to-end. Run `pytest` after pulling this
and paste back any failures - most likely candidates for a mismatch are
exact status codes or response field names drifting from what's assumed
here as the codebase evolves.

## Notes
- **New model, no migration included on purpose**: `LoginEvent` (login/device
  history) was added to `apps/authentication/models.py` but there's no
  matching migration file in this zip. Your local `migrations/` folder has
  likely already drifted from a fresh install at this point (e.g. an
  auto-generated `0002_alter_user_managers.py` from an earlier
  `makemigrations` run) - hand-writing a numbered migration here risked
  colliding with whatever's already in your folder, the exact "multiple
  leaf nodes" problem from earlier in this project's history. Instead:
  ```bash
  python manage.py makemigrations authentication
  python manage.py migrate
  ```
  Django will generate the correct migration against whatever's actually in
  your local migration history, not a guess from over here.
- The Django admin (`/admin/`) now uses django-unfold - a modern Tailwind-based
  theme, branded green to match the app - instead of the default Django look.
  Nothing to configure; it applies automatically once `pip install -r
  requirements.txt` picks up the new dependency. Branding/colors live in
  `UNFOLD` in `settings.py`.
- **Admin dashboard** (`/admin/`, the index page) is a custom platform-wide
  overview (`vendoriq/admin_dashboard.py` + `templates/admin/index.html`) -
  users, stores, revenue, growth trends, store health, top performers, AI
  usage, and login history, all from real data. It also has a **Planned**
  section (platform revenue/subscriptions, support, system health) with
  dashed-border placeholder cards showing "—" instead of numbers - these
  intentionally aren't wired to anything, since the underlying features
  (billing, support tickets, uptime monitoring) don't exist yet. Build the
  feature, then replace the em-dashes in `admin_dashboard.py` with real
  queries and drop the `-planned` CSS classes in the template.
- Django runs on port 8000 instead of 5000
- Update frontend VITE_API_URL or vite proxy target accordingly
- Migrations are committed - after pulling model changes, just run
  `python manage.py migrate` locally (only run `makemigrations` yourself
  if you change a model, then commit the generated file)
