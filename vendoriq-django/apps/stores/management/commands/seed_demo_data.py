"""
Generates realistic dummy data so you can actually load-test the app instead
of guessing at its capacity.

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --stores 20 --products 80 --days 90 --sales-per-day 40
    python manage.py seed_demo_data --wipe   # delete previously seeded demo data first

Every seeded user's password is "Demo1234!" (printed at the end alongside a
CSV of every login), and every seeded record is tagged so --wipe can find
and remove it without touching real data: store names all start with
"[DEMO]" and users all have emails ending in "@demo.vendoriq.test".
"""
import csv
import random
import sys
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import User
from apps.stores.models import Store, Staff
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem
from apps.expenses.models import Expense
from apps.invoices.models import Invoice, InvoiceItem

DEMO_PASSWORD = 'Demo1234!'
DEMO_EMAIL_SUFFIX = '@demo.vendoriq.test'
DEMO_STORE_PREFIX = '[DEMO] '

FIRST_NAMES = ['Adaeze', 'Chinedu', 'Ngozi', 'Emeka', 'Fatima', 'Ibrahim', 'Yemi', 'Tunde',
               'Aisha', 'Kelechi', 'Blessing', 'Segun', 'Amaka', 'Musa', 'Folake', 'Uche',
               'Bisi', 'Chidi', 'Zainab', 'Obinna']
LAST_NAMES = ['Okafor', 'Adeyemi', 'Balogun', 'Eze', 'Mohammed', 'Okoro', 'Bello', 'Nwosu',
              'Afolabi', 'Ibrahim', 'Chukwu', 'Suleiman', 'Adebayo', 'Umeh', 'Yusuf']

STORE_TYPES = ['Provisions Store', 'Supermarket', 'Pharmacy', 'Boutique', 'Electronics Shop',
               'Hardware Store', 'Bookshop']
CITIES = ['Lagos', 'Abuja', 'Ibadan', 'Kano', 'Port Harcourt', 'Enugu', 'Benin City']

PRODUCT_CATALOG = {
    'Cooking Oil': ['Kings Vegetable Oil 1L', 'Devon Groundnut Oil 5L', 'Power Oil 1L', 'Mamador Oil 750ml'],
    'Grains & Rice': ['Mama Gold Rice 50kg', 'Royal Stallion Rice 25kg', 'Ofada Rice 10kg', 'Golden Penny Semovita 10kg'],
    'Dairy': ['Peak Milk Tin', 'Three Crowns Milk Sachet', 'Loya Milk 400g', 'Cowbell Milk 900g'],
    'Beverages': ['Bournvita 500g', 'Milo 400g', 'Lipton Tea 100 bags', 'Nescafe Classic 200g'],
    'Snacks': ['Gala Sausage Roll', 'Digestive Biscuits', 'Indomie Noodles Carton', 'Cabin Biscuits'],
    'Household': ['Omo Detergent 1kg', 'Sunlight Soap', 'Harpic Toilet Cleaner', 'Dettol Antiseptic 250ml'],
    'Personal Care': ['Dudu Osun Soap', 'Close Up Toothpaste', 'Nivea Lotion 400ml', 'Always Sanitary Pads'],
    'Frozen Foods': ['Frozen Chicken 1kg', 'Titus Fish Pack', 'Frozen Turkey Wings'],
    'Bakery': ['Sliced Bread Loaf', 'Meat Pie Pack', 'Doughnuts (6pcs)'],
}

EXPENSE_TEMPLATES = [
    ('RENT', 'Shop rent', True, 45000, 120000),
    ('UTILITIES', 'Electricity (PHCN + generator fuel)', True, 8000, 25000),
    ('SALARIES', 'Staff salaries', True, 30000, 90000),
    ('TRANSPORT', 'Goods delivery/transport', False, 2000, 8000),
    ('PACKAGING', 'Nylon bags & packaging', False, 1500, 6000),
    ('MAINTENANCE', 'Shop repairs/maintenance', False, 3000, 15000),
    ('MISCELLANEOUS', 'Miscellaneous', False, 1000, 5000),
]


class Command(BaseCommand):
    help = 'Seed realistic dummy data (stores, products, sales, expenses, invoices) for load testing.'

    def add_arguments(self, parser):
        parser.add_argument('--stores', type=int, default=10, help='Number of demo stores to create (default 10)')
        parser.add_argument('--products', type=int, default=40, help='Products per store (default 40)')
        parser.add_argument('--staff', type=int, default=4, help='Staff members per store, besides the owner (default 4)')
        parser.add_argument('--days', type=int, default=60, help='How many days of sales/expense history to backfill (default 60)')
        parser.add_argument('--sales-per-day', type=int, default=25, help='Average sales recorded per store per day (default 25)')
        parser.add_argument('--invoices', type=int, default=15, help='Invoices per store (default 15)')
        parser.add_argument('--wipe', action='store_true', help='Delete all previously seeded [DEMO] data first, then exit')
        parser.add_argument('--seed', type=int, default=None, help='Random seed, for reproducible runs')
        parser.add_argument('--csv-out', type=str, default='demo_logins.csv', help='Where to write the generated login CSV')

    def handle(self, *args, **options):
        if options['seed'] is not None:
            random.seed(options['seed'])

        if options['wipe']:
            self.wipe()
            return

        n_stores = options['stores']
        n_products = options['products']
        n_staff = options['staff']
        n_days = options['days']
        sales_per_day = options['sales_per_day']
        n_invoices = options['invoices']

        self.stdout.write(self.style.WARNING(
            f'Seeding {n_stores} stores x ({n_products} products, {n_staff} staff, '
            f'~{sales_per_day}/day sales over {n_days} days, {n_invoices} invoices)...'
        ))

        rows = []  # for the login CSV
        total_sales = 0
        total_products = 0

        for i in range(n_stores):
            with transaction.atomic():
                owner = self._make_user(f'owner{i}')
                store = Store.objects.create(
                    name=f'{DEMO_STORE_PREFIX}{random.choice(CITIES)} {random.choice(STORE_TYPES)} {i+1}',
                    location=random.choice(CITIES),
                    owner=owner,
                )
                rows.append([store.name, owner.email, DEMO_PASSWORD, 'OWNER'])

                staff_users = []
                for j in range(n_staff):
                    role = random.choice(['MANAGER', 'CASHIER', 'CASHIER'])
                    user = self._make_user(f'store{i}staff{j}')
                    Staff.objects.create(store=store, user=user, role=role)
                    staff_users.append(user)
                    rows.append([store.name, user.email, DEMO_PASSWORD, role])

                products = self._make_products(store, n_products)
                total_products += len(products)

            # Sales/expenses/invoices happen in their own transactions per day
            # so one huge multi-thousand-row transaction doesn't hold locks
            # for ages - closer to how real traffic actually writes.
            total_sales += self._make_sales(store, products, staff_users + [owner], n_days, sales_per_day)
            self._make_expenses(store, n_days)
            self._make_invoices(store, products, n_invoices)

            self.stdout.write(f'  [{i+1}/{n_stores}] {store.name} done')

        csv_path = options['csv_out']
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['store', 'email', 'password', 'role'])
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {n_stores} stores, {total_products} products, {total_sales} sales.\n'
            f'Every login uses password: {DEMO_PASSWORD}\n'
            f'Full login list written to: {csv_path}\n'
            f'Run again with --wipe to remove all of this later.'
        ))

    # --- helpers -------------------------------------------------------

    def _make_user(self, tag):
        email = f'{tag}{DEMO_EMAIL_SUFFIX}'
        name = f'{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}'
        user, _ = User.objects.update_or_create(
            email=email,
            defaults={'name': name, 'phone': f'080{random.randint(10000000, 99999999)}'},
        )
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def _make_products(self, store, count):
        products = []
        catalog_items = [(cat, item) for cat, items in PRODUCT_CATALOG.items() for item in items]
        for n in range(count):
            category, base_name = random.choice(catalog_items)
            cost = Decimal(random.randint(200, 15000))
            markup = Decimal(str(round(random.uniform(1.15, 1.6), 2)))
            selling = (cost * markup).quantize(Decimal('1'))
            products.append(Product(
                store=store,
                name=f'{base_name} #{n+1}' if n >= len(catalog_items) else base_name,
                barcode=str(random.randint(1000000000000, 9999999999999)),
                cost_price=cost,
                selling_price=selling,
                quantity=random.randint(0, 200),
                low_stock_threshold=random.choice([5, 10, 15]),
                category=category,
                supplier=f'{random.choice(LAST_NAMES)} Distributors',
            ))
        return Product.objects.bulk_create(products)

    def _make_sales(self, store, products, recorders, n_days, sales_per_day):
        in_stock = [p for p in products if p.quantity > 0]
        if not in_stock:
            return 0
        now = timezone.now()
        count = 0
        for day_offset in range(n_days, -1, -1):
            day = now - timedelta(days=day_offset)
            n_today = max(0, int(random.gauss(sales_per_day, sales_per_day * 0.3)))
            plan = []  # (Sale instance, intended_datetime, product, qty, unit_price, unit_cost, profit)
            for _ in range(n_today):
                product = random.choice(in_stock)
                qty = random.randint(1, 5)
                unit_price = product.selling_price
                unit_cost = product.cost_price
                amount = unit_price * qty
                profit = (unit_price - unit_cost) * qty
                sale_time = day.replace(
                    hour=random.randint(8, 20), minute=random.randint(0, 59), second=random.randint(0, 59)
                )
                sale = Sale(
                    store=store, recorded_by=random.choice(recorders),
                    total_amount=amount, total_profit=profit,
                    subtotal=amount, amount_paid=amount,  # POS fields: no discount, paid in full
                )
                plan.append((sale, sale_time, product, qty, unit_price, unit_cost, profit))

            if not plan:
                continue

            created_sales = Sale.objects.bulk_create([p[0] for p in plan])
            # bulk_create runs each auto_now_add field's pre_save() (add=True),
            # which unconditionally stamps created_at = now() regardless of
            # what we set above - so right after insert, every row's
            # created_at is "now", not the historical date we intended.
            # Restore the real dates with bulk_update, which (unlike
            # bulk_create) does NOT re-run auto_now_add's pre_save logic -
            # it writes exactly the attribute value currently on the object.
            for (sale, sale_time, *_), created in zip(plan, created_sales):
                created.created_at = sale_time
            Sale.objects.bulk_update(created_sales, ['created_at'])

            item_batch = [
                SaleItem(sale=created, product=product, quantity=qty, unit_price=unit_price, unit_cost=unit_cost, profit=profit)
                for (_, _, product, qty, unit_price, unit_cost, profit), created in zip(plan, created_sales)
            ]
            SaleItem.objects.bulk_create(item_batch)
            count += len(created_sales)
        return count

    def _make_expenses(self, store, n_days):
        now = timezone.now()
        expenses = []
        for day_offset in range(n_days, -1, -1):
            day = (now - timedelta(days=day_offset)).date()
            if day.day == 1:  # monthly overhead on the 1st
                for category, desc, is_overhead, lo, hi in EXPENSE_TEMPLATES[:3]:
                    expenses.append(Expense(
                        store=store, category=category, description=desc,
                        amount=Decimal(random.randint(lo, hi)), frequency='MONTHLY',
                        is_overhead=is_overhead, incurred_on=day,
                    ))
            if random.random() < 0.4:  # a handful of misc expenses on other days
                category, desc, is_overhead, lo, hi = random.choice(EXPENSE_TEMPLATES[3:])
                expenses.append(Expense(
                    store=store, category=category, description=desc,
                    amount=Decimal(random.randint(lo, hi)), frequency='ONE_OFF',
                    is_overhead=is_overhead, incurred_on=day,
                ))
        Expense.objects.bulk_create(expenses)

    def _make_invoices(self, store, products, count):
        in_stock = [p for p in products if p.quantity > 0] or products
        for _ in range(count):
            product = random.choice(in_stock)
            qty = random.randint(1, 4)
            invoice = Invoice.objects.create(
                store=store,
                customer_name=f'{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}',
                customer_email=f'customer{random.randint(1000,9999)}{DEMO_EMAIL_SUFFIX}',
                customer_phone=f'080{random.randint(10000000, 99999999)}',
                total_amount=product.selling_price * qty,
                status=random.choice(['DRAFT', 'SENT', 'SENT', 'PAID', 'PAID']),
            )
            InvoiceItem.objects.create(invoice=invoice, product=product, quantity=qty, unit_price=product.selling_price)

    def wipe(self):
        stores = Store.objects.filter(name__startswith=DEMO_STORE_PREFIX)
        users = User.objects.filter(email__iendswith=DEMO_EMAIL_SUFFIX)
        n_stores, n_users = stores.count(), users.count()
        if not n_stores and not n_users:
            self.stdout.write('No demo data found.')
            return
        confirm = input(f'This will permanently delete {n_stores} demo store(s) and {n_users} demo user(s). Type "yes" to continue: ')
        if confirm.strip().lower() != 'yes':
            self.stdout.write('Aborted.')
            sys.exit(1)
        stores.delete()  # cascades to products/sales/expenses/invoices/staff
        users.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {n_stores} demo store(s) and {n_users} demo user(s).'))
