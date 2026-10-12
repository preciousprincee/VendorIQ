"""
python manage.py check_live_config [--send-test-email you@example.com] [--send-test-sms 08012345678]

Checks that the REAL keys this server is configured with actually work, before customers find out:
  * database- connects to Neon, reports pooled vs direct, and lists any migrations not yet applied
  * storage - writes, reads back through the PUBLIC address, then deletes a tiny file in Cloudflare R2
  * email   - asks Resend to validate the API key and that your sender domain is verified (sends nothing
              unless --send-test-email is given)
  * SMS     - asks Termii for your balance (sends nothing unless --send-test-sms is given)
  * Paystack- asks Paystack for your balance with the secret key (read-only), and checks the
              secret and public key belong to the same mode (both live, or both test)
  * safety  - DEBUG off, the demo upgrade off, a real SECRET_KEY

Run it ON THE SERVER (Render > vendoriq-api > Shell) so it uses exactly the environment the app uses.
Exit code is 1 if anything failed, so it can also gate a deploy.
"""
import time
import uuid

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.core.management.base import BaseCommand

from apps.authentication import sms
from apps.authentication.phone import normalize_phone
from vendoriq import infra


class Command(BaseCommand):
    help = 'Verify that the live email, SMS and Paystack credentials actually work.'

    def add_arguments(self, parser):
        parser.add_argument('--send-test-email', metavar='ADDRESS', help='Also send one real test email to this address.')
        parser.add_argument('--send-test-sms', metavar='PHONE', help='Also send one real test SMS to this Nigerian number.')

    def handle(self, *args, **opts):
        self.failures = 0
        self.stdout.write(self.style.MIGRATE_HEADING('\nVendorIQ live-mode check\n'))
        self._safety()
        self._database()
        self._storage()
        self._email(opts.get('send_test_email'))
        self._sms(opts.get('send_test_sms'))
        self._paystack()
        self._optional_services()
        self.stdout.write('')
        if self.failures:
            self.stdout.write(self.style.ERROR(f'{self.failures} problem(s) found - fix them before going live.'))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS('All checks passed.'))

    # -- helpers -------------------------------------------------------------
    def ok(self, msg):
        self.stdout.write(self.style.SUCCESS(f'  [ OK ] {msg}'))

    def warn(self, msg):
        self.stdout.write(self.style.WARNING(f'  [WARN] {msg}'))

    def fail(self, msg):
        self.failures += 1
        self.stdout.write(self.style.ERROR(f'  [FAIL] {msg}'))

    # -- checks --------------------------------------------------------------
    def _safety(self):
        self.stdout.write('Safety')
        (self.fail if settings.DEBUG else self.ok)('DEBUG is ' + ('ON - turn it off in production' if settings.DEBUG else 'off'))
        (self.fail if settings.ALLOW_MOCK_UPGRADE else self.ok)(
            'Demo upgrade (free Pro) is ' + ('ON - anyone could get Pro for free; unset ALLOW_MOCK_UPGRADE' if settings.ALLOW_MOCK_UPGRADE else 'off'))
        if 'insecure' in settings.SECRET_KEY:
            self.fail('SECRET_KEY is still the placeholder value')
        else:
            self.ok('SECRET_KEY is set')
        if not settings.FRONTEND_URL:
            self.warn('FRONTEND_URL is empty (links and logos in emails will be wrong)')
        else:
            self.ok(f'FRONTEND_URL = {settings.FRONTEND_URL}')

    def _database(self):
        import os
        self.stdout.write('\nDatabase (Neon PostgreSQL)')
        db = settings.DATABASES['default']
        if 'sqlite' in db['ENGINE']:
            (self.fail if not settings.DEBUG else self.warn)('Using SQLite - set DATABASE_URL to your Neon POOLED connection string')
            return
        host = db.get('HOST', '')
        pooled = infra.is_neon_pooled(os.environ.get('DATABASE_URL', ''))
        if not infra.is_neon(os.environ.get('DATABASE_URL', '')):
            self.warn(f'Database host {host!r} is not a Neon address (*.neon.tech) - fine if intended, but this guide assumes Neon')
        elif pooled:
            self.ok('DATABASE_URL is the Neon POOLED connection (good for the running app)')
        else:
            self.warn('DATABASE_URL is a Neon DIRECT connection - use the pooled one (host contains "-pooler") for the app')
        for w in infra.database_warnings(os.environ, ['manage.py', 'check']):
            if 'DIRECT connection' not in w:
                self.warn(w)
        try:
            started = time.monotonic()
            with connection.cursor() as cursor:
                cursor.execute('SELECT version()')
                version = cursor.fetchone()[0].split(',')[0]
            self.ok(f'Connected ({version}) in {int((time.monotonic() - started) * 1000)} ms - the first call after idle can be slower while Neon wakes up')
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                self.fail(f'{len(plan)} migration(s) not applied yet - run `python manage.py migrate` (with DATABASE_URL_DIRECT set)')
            else:
                self.ok('All migrations are applied')
        except Exception as exc:
            self.fail(f'Could not use the database: {exc}')

    def _storage(self):
        self.stdout.write('\nFile storage (Cloudflare R2, product photos)')
        backend = settings.STORAGES['default']['BACKEND']
        if not backend.endswith('S3Storage'):
            (self.fail if not settings.DEBUG else self.warn)('Photos are stored on the local disk - set the R2_* variables (the disk is erased on every deploy)')
            return
        opts = settings.STORAGES['default']['OPTIONS']
        self.ok(f'R2 bucket "{opts["bucket_name"]}" via {opts["endpoint_url"]}')
        warning = infra.r2_public_host_warning({'R2_PUBLIC_URL': opts.get('custom_domain', '')})
        if warning:
            self.warn(warning)
        name = f'healthcheck/{uuid.uuid4().hex}.txt'
        try:
            saved = default_storage.save(name, ContentFile(b'vendoriq-ok'))
            self.ok('Wrote a test file to the bucket (the access key and secret work, and have write permission)')
        except Exception as exc:
            self.fail(f'Could not write to the bucket: {exc}. Check the API token has Object Read & Write on this bucket, and the Account ID.')
            return
        try:
            url = default_storage.url(saved)
            r = requests.get(url, timeout=15)
            if r.status_code == 200 and r.content == b'vendoriq-ok':
                self.ok(f'The test file is publicly readable at {url.rsplit("/", 1)[0]}/ - photos will display')
            else:
                self.fail(f'Wrote the file but the PUBLIC address answered HTTP {r.status_code} ({url}). Connect the custom domain to the bucket '
                          '(R2 > bucket > Settings > Public access) and make sure R2_PUBLIC_URL is that domain.')
        except Exception as exc:
            self.fail(f'Could not read the test file through R2_PUBLIC_URL: {exc}')
        finally:
            try:
                default_storage.delete(saved)
            except Exception:
                self.warn(f'Could not delete the test file {saved} - remove it from the bucket by hand')

    def _email(self, send_to):
        from email.utils import parseaddr
        self.stdout.write('\nEmail (verification codes, invoices, via Resend)')
        key = settings.RESEND_API_KEY
        if not key:
            self.fail('RESEND_API_KEY is not set - verification emails would not be delivered')
            return
        if not key.startswith('re_'):
            self.warn('RESEND_API_KEY does not start with "re_" - check you copied the API key, not something else')
        sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
        domain = sender.rsplit('@', 1)[-1].lower() if '@' in sender else ''
        if not domain:
            self.fail(f'DEFAULT_FROM_EMAIL ("{settings.DEFAULT_FROM_EMAIL}") is not a valid sender address')
            return
        try:
            r = requests.get('https://api.resend.com/domains', headers={'Authorization': f'Bearer {key}'}, timeout=15)
            data = r.json() if r.content else {}
        except Exception as exc:
            self.fail(f'Could not reach Resend: {exc}')
            return
        if r.status_code == 200:
            self.ok('Resend accepted the API key (full access)')
            mine = next((d for d in data.get('data', []) if (d.get('name') or '').lower() == domain), None)
            if domain == 'resend.dev':
                self.warn('Sending from resend.dev works only for your own account email - use your own verified domain for customers')
            elif mine is None:
                self.fail(f'The sender domain "{domain}" is not added in Resend. Add it at resend.com/domains and publish the DNS records.')
            elif mine.get('status') != 'verified':
                self.fail(f'Domain "{domain}" is in Resend but its status is "{mine.get("status")}" - finish the DNS verification')
            else:
                self.ok(f'Sender domain "{domain}" is verified in Resend')
        elif r.status_code in (401, 403) and 'restricted' in str(data).lower():
            self.ok('Resend accepted the API key (Sending-only: it can send, but cannot list domains)')
            self.warn(f'Cannot pre-check that "{domain}" is verified with a Sending-only key. Prove it with --send-test-email.')
        elif r.status_code in (401, 403):
            self.fail(f'Resend rejected the API key (HTTP {r.status_code}): {str(data)[:160]}')
            return
        else:
            self.fail(f'Resend returned HTTP {r.status_code}: {str(data)[:160]}')
            return
        if send_to:
            try:
                send_mail('VendorIQ test email', 'If you can read this, live email works.', None, [send_to], fail_silently=False)
                self.ok(f'Resend accepted a test email for {send_to} - check the inbox (and spam)')
            except Exception as exc:
                self.fail(f'Test email failed: {exc}')

    def _sms(self, send_to):
        self.stdout.write('\nSMS (phone verification codes, via Termii)')
        if not settings.TERMII_API_KEY:
            self.fail('TERMII_API_KEY is not set - phone verification would be unavailable')
            return
        try:
            r = requests.get(f'{settings.TERMII_BASE_URL}/api/get-balance', params={'api_key': settings.TERMII_API_KEY}, timeout=10)
            data = r.json() if r.content else {}
        except Exception as exc:
            self.fail(f'Could not reach Termii at {settings.TERMII_BASE_URL}: {exc}')
            return
        if r.status_code != 200 or 'balance' not in data:
            self.fail(f'Termii rejected the key (HTTP {r.status_code}): {str(data)[:200]}. If your dashboard shows a different base URL, set TERMII_BASE_URL.')
            return
        balance = data.get('balance')
        self.ok(f'Termii key accepted. Balance: {balance} {data.get("currency", "")}'.strip())
        try:
            if float(balance) < 500:
                self.warn('Balance is low - each verification SMS costs credit, and signups stop working at zero')
        except (TypeError, ValueError):
            pass
        self.warn(f'Sender ID is "{settings.TERMII_SENDER_ID}" on the "{settings.TERMII_CHANNEL}" route - it must be approved on your Termii account. Prove it with --send-test-sms.')
        if send_to:
            number = normalize_phone(send_to)
            if not number:
                self.fail(f'"{send_to}" is not a valid Nigerian number')
                return
            try:
                sms.send_sms(number, 'VendorIQ test message: live SMS works.')
                self.ok(f'Termii accepted a test SMS to {number} - it should arrive within a minute')
            except Exception as exc:
                self.fail(f'Test SMS failed: {exc}')

    def _paystack(self):
        self.stdout.write('\nPaystack (subscriptions, referral payouts)')
        sk, pk = settings.PAYSTACK_SECRET_KEY, settings.PAYSTACK_PUBLIC_KEY
        if not (sk and pk):
            self.fail('PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY must BOTH be set')
            return
        mode = lambda k: 'live' if '_live_' in k else 'test' if '_test_' in k else 'unknown'
        if mode(sk) != mode(pk):
            self.fail(f'Secret key is {mode(sk)} but public key is {mode(pk)} - use the matching pair')
        else:
            (self.ok if mode(sk) == 'live' else self.warn)(f'Keys are in {mode(sk).upper()} mode' + ('' if mode(sk) == 'live' else ' - real customers cannot pay until you switch to the live keys'))
        try:
            r = requests.get('https://api.paystack.co/balance', headers={'Authorization': f'Bearer {sk}'}, timeout=15)
            data = r.json() if r.content else {}
        except Exception as exc:
            self.fail(f'Could not reach Paystack: {exc}')
            return
        if r.status_code == 200 and data.get('status'):
            ngn = next((b.get('balance') for b in data.get('data', []) if b.get('currency') == 'NGN'), None)
            self.ok('Paystack accepted the secret key' + (f'. NGN balance: N{ngn / 100:,.2f}' if isinstance(ngn, (int, float)) else ''))
            self.warn('Referral payouts are paid out of this balance. Keep it funded, or keep referrals switched off in admin.')
        elif r.status_code == 401:
            self.fail('Paystack says the secret key is invalid (401) - copy it again from Dashboard > Settings > API Keys')
        else:
            self.fail(f'Paystack returned HTTP {r.status_code}: {str(data)[:200]}')
        self.warn('Also confirm in the Paystack dashboard (same mode) that the webhook URL is https://<your-api>/api/billing/paystack-webhook/ '
                  'and your account is activated for live payments.')

    def _optional_services(self):
        self.stdout.write('\nOptional services (their features simply stay off when unset)')
        groq = getattr(settings, 'GROQ_API_KEY', '')
        if not groq:
            self.warn('GROQ_API_KEY not set - the AI Assistant will be unavailable')
        else:
            try:
                r = requests.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {groq}'}, timeout=15)
                (self.ok if r.status_code == 200 else self.fail)(
                    'Groq accepted the key (AI Assistant will work)' if r.status_code == 200 else f'Groq rejected the key (HTTP {r.status_code})')
            except Exception as exc:
                self.fail(f'Could not reach Groq: {exc}')
        google = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {}) if hasattr(settings, 'SOCIALACCOUNT_PROVIDERS') else {}
        cid, secret = google.get('client_id', ''), google.get('secret', '')
        if not (cid and secret):
            self.warn('Google sign-in is not configured (GOOGLE_OAUTH_CLIENT_ID / _SECRET) - the button will not work')
        else:
            try:
                # A deliberately bogus code: Google answers invalid_grant if the CLIENT is valid and invalid_client if not.
                r = requests.post('https://oauth2.googleapis.com/token', data={
                    'client_id': cid, 'client_secret': secret, 'code': 'x', 'grant_type': 'authorization_code',
                    'redirect_uri': 'postmessage'}, timeout=15)
                err = (r.json() or {}).get('error', '')
                if err == 'invalid_client':
                    self.fail('Google says the client id / secret pair is invalid')
                else:
                    self.ok('Google accepted the client id and secret')
            except Exception as exc:
                self.fail(f'Could not reach Google: {exc}')
