# Load testing VendorIQ

Two pieces: dummy data to test against, and a script that actually throws
concurrent traffic at the API so you get a real number instead of a guess.

## 1. Seed dummy data

From the `vendoriq-django` project root, with your virtualenv active and
`DATABASE_URL` pointed at whichever environment you want to test (local,
staging, or - carefully - production):

```bash
python manage.py seed_demo_data --stores 20 --products 60 --days 90 --sales-per-day 40 --invoices 20
```

This creates, per store: an owner, a handful of staff (managers/cashiers),
a product catalog, 90 days of backdated sales (so the dashboard/trend charts
have real history instead of one flat day), expenses, and invoices.

- Every seeded user's password is `Demo1234!`
- Every login is written to `demo_logins.csv` (email, password, role, store)
- Every seeded store name starts with `[DEMO]` and every seeded user's email
  ends in `@demo.vendoriq.test` - both exist specifically so you can find and
  remove all of it later without touching real data:

```bash
python manage.py seed_demo_data --wipe
```

Run `python manage.py seed_demo_data --help` for all options (`--seed` for a
reproducible run, `--csv-out` to change the output path, etc).

**Don't run this against a real production database with real customers in
it** unless you immediately `--wipe` it afterward - it's for a
staging/throwaway environment, or a prod database you're comfortable
cleaning up.

## 2. Load test with Locust

```bash
pip install locust   # not a production dependency, so it's not in requirements.txt
cd loadtest
locust -f locustfile.py --host https://vendoriq-api.onrender.com
```

Open http://localhost:8089, set the number of users (e.g. 2000) and spawn
rate (e.g. 50/sec), and start the test. It logs in as a random mix of the
seeded owners/managers/cashiers and hits the same endpoints the real app
does (dashboard, products, sales, trend, notifications, invoices, and
occasionally records an actual sale) at a human-like pace, not
zero-wait-time hammering.

Or headless, straight to a CSV report:

```bash
locust -f locustfile.py --host https://vendoriq-api.onrender.com \
  --users 2000 --spawn-rate 50 --run-time 5m --headless --csv=results
```

### What to look at
- **p95/p99 response time** in the Locust UI (or `results_stats.csv`) - this
  is the real answer to "can it handle N concurrent users", not a guess from
  reading the code.
- **Failure %** - anything above ~0-1% under sustained load means something
  is falling over (DB connection limit, Redis, gunicorn workers maxed out).
- Watch your Render/Supabase/Redis dashboards during the run - CPU, memory,
  and DB connection count will tell you which piece hits its ceiling first.
- If you hit the default throttle (`THROTTLE_RATE_USER=300/min` per user),
  Locust will show 429s - that's the rate limiter working as designed, not a
  capacity failure; raise it via env var if you want to test past it.

If the numbers aren't good enough yet, the usual next steps in order of
impact: bump the Render web service plan/`WEB_CONCURRENCY`, bump the Redis
plan, bump the Supabase pooler's connection limit.
