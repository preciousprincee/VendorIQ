"""
Simulates many concurrent real users hitting the live API - the actual test
of "can this handle thousands of users at once", as opposed to just having
rows in the database.

Setup:
    1. Seed data first (from the vendoriq-django project root, with your
       venv active and DATABASE_URL pointed at the environment you want to
       test):
           python manage.py seed_demo_data --stores 20 --sales-per-day 40
       This writes demo_logins.csv - loadtest/locustfile.py reads it to log
       in as a random mix of real seeded owners/managers/cashiers rather
       than hammering one account.

    2. Install locust (not a production dependency, so it's not in
       requirements.txt): pip install locust

    3. Point it at your target and run:
           cd loadtest
           locust -f locustfile.py --host https://vendoriq-api.onrender.com
       Then open http://localhost:8089, set "number of users" (e.g. 2000)
       and "spawn rate" (e.g. 50/sec), and start the test.

       Or headless, straight to a report:
           locust -f locustfile.py --host https://vendoriq-api.onrender.com \
               --users 2000 --spawn-rate 50 --run-time 5m --headless \
               --csv=results

    Watch p95/p99 response time and failure % in the web UI (or results.csv
    with --csv) - that's your real answer to "can it handle N concurrent
    users", not a guess from reading the code.
"""
import csv
import os
import random

from locust import HttpUser, task, between, events

LOGINS_CSV = os.getenv('DEMO_LOGINS_CSV', 'demo_logins.csv')
_logins = []


@events.test_start.add_listener
def _load_logins(environment, **kwargs):
    global _logins
    try:
        with open(LOGINS_CSV, newline='') as f:
            _logins = list(csv.DictReader(f))
    except FileNotFoundError:
        raise SystemExit(
            f'\n"{LOGINS_CSV}" not found. Run `python manage.py seed_demo_data` first '
            f'(from the vendoriq-django project), or set DEMO_LOGINS_CSV to its path.\n'
        )
    if not _logins:
        raise SystemExit(f'"{LOGINS_CSV}" has no rows - re-run seed_demo_data.')
    print(f'Loaded {len(_logins)} demo logins from {LOGINS_CSV}')


class VendorIQUser(HttpUser):
    # Real users don't hammer the API back-to-back - a couple of seconds
    # between actions (reading a screen, typing a barcode, etc.) is closer
    # to reality than zero wait time, and won't produce a misleadingly
    # apocalyptic result for "thousands of users" who aren't all mashing
    # refresh in the same millisecond.
    wait_time = between(1, 4)

    def on_start(self):
        login = random.choice(_logins)
        self.role = login['role']
        resp = self.client.post('/api/auth/login/', json={
            'email': login['email'], 'password': login['password'],
        }, name='/api/auth/login/')
        if resp.status_code != 200:
            self.environment.runner.quit()
            raise SystemExit(f'Login failed for {login["email"]}: {resp.status_code} {resp.text[:200]}')
        data = resp.json()
        self.token = data['token']
        self.client.headers.update({'Authorization': f'Bearer {self.token}'})

        resp = self.client.get('/api/stores/', name='/api/stores/').json()
        stores = resp.get('owned', []) + resp.get('staff', [])
        if not stores:
            self.environment.runner.quit()
            raise SystemExit(f'No stores returned for {login["email"]}')
        self.store_id = random.choice(stores)['id']

    # --- Read-heavy tasks, weighted roughly like real usage --------------

    @task(6)
    def view_products(self):
        self.client.get(f'/api/stores/{self.store_id}/products/', name='/products/')

    @task(5)
    def view_sales(self):
        self.client.get(f'/api/stores/{self.store_id}/sales/', name='/sales/')

    @task(4)
    def view_dashboard(self):
        if self.role == 'CASHIER':
            return  # cashiers don't have dashboard access - matches real permissions
        self.client.get(f'/api/stores/{self.store_id}/insights/dashboard/', name='/insights/dashboard/')

    @task(3)
    def view_trend(self):
        if self.role == 'CASHIER':
            return
        days = random.choice([7, 30, 90])
        self.client.get(f'/api/stores/{self.store_id}/insights/trend/?days={days}', name='/insights/trend/')

    @task(2)
    def view_notifications(self):
        if self.role == 'CASHIER':
            return
        self.client.get(f'/api/stores/{self.store_id}/insights/notifications/', name='/insights/notifications/')

    @task(1)
    def view_invoices(self):
        self.client.get(f'/api/stores/{self.store_id}/invoices/', name='/invoices/')

    # --- The one write path, at realistic frequency (most page views don't
    # result in a sale) ---------------------------------------------------

    @task(2)
    def record_sale(self):
        products = self.client.get(f'/api/stores/{self.store_id}/products/', name='/products/').json().get('products', [])
        in_stock = [p for p in products if p['quantity'] > 0]
        if not in_stock:
            return
        product = random.choice(in_stock)
        self.client.post(
            f'/api/stores/{self.store_id}/sales/',
            json={'items': [{'productId': product['id'], 'quantity': random.randint(1, 2)}]},
            name='/sales/ [POST]',
        )
