# VendorIQ

Multi-tenant inventory and sales management platform for small retail
businesses in Nigeria.

- **`vendoriq-django/`** — Django REST API backend. See its own
  [README](vendoriq-django/README.md) for setup, testing, and deployment.
- **`vendoriq-frontend/`** — React (Vite) single-page app.

## CI/CD

**CI** (`.github/workflows/ci.yml`, GitHub Actions): runs on every push and
every pull request against `main`.
- `backend-tests` — installs backend deps, runs migrations and the full
  `pytest` suite against a real Postgres + Redis (matching production, not
  SQLite), so a passing run means something.
- `frontend-build` — installs frontend deps and runs `npm run build`, to
  catch a broken build before it reaches anyone.

**CD**: handled by **Render's own native auto-deploy**, not by GitHub
Actions - Render already does this well for free, so this doesn't reinvent
it with a custom deploy script and an API-key secret to manage. In the
Render dashboard, for each service (`vendoriq-api`, `vendoriq-celery-worker`):
Settings → Build & Deploy → Auto-Deploy → **On Commit**. Every push to
`main` then deploys automatically.

### Wiring CI and CD together (do this once)

Right now, nothing stops a push straight to `main` with a broken test from
deploying — Render doesn't know or care whether CI passed. Fix that with a
GitHub branch protection rule:

1. GitHub repo → **Settings → Branches → Add branch protection rule**
2. Branch name pattern: `main`
3. Enable **"Require status checks to pass before merging"**
4. Search for and select both `backend-tests` and `frontend-build` (they
   only appear in this list after the workflow has run at least once - push
   once first, then come back and add this rule)
5. Enable **"Require a pull request before merging"** so nothing lands on
   `main` without going through a PR (and therefore through CI) at all

After this: push to a branch → open a PR → CI runs automatically → PR can
only be merged once both jobs are green → merging to `main` triggers
Render's auto-deploy. That's the full loop, without any deploy credentials
living in GitHub Actions at all.

### Required secrets

None, for CI as configured - it uses placeholder values for
`SECRET_KEY`/`GROQ_API_KEY` scoped to the test run only (see `ci.yml`),
never anything real. Deployment secrets (`DATABASE_URL`, `GROQ_API_KEY`,
email credentials, etc.) live in the Render dashboard, per the backend
README's deployment section - not in GitHub at all, since Render's
auto-deploy doesn't need them there.
