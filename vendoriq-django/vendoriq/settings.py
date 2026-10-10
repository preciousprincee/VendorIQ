from pathlib import Path
from datetime import timedelta
import os
import sys
import dj_database_url
from dotenv import load_dotenv
from django.urls import reverse_lazy
from django.utils.text import format_lazy
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-vendoriq-change-this-in-production-xyz')
# Secure by default: if DEBUG is missing from the environment (a forgotten
# variable on a new host) the app must NOT come up in debug mode - that
# exposes settings, SQL and source in error pages. Local development sets
# DEBUG=True explicitly in .env (see .env.example).
DEBUG = os.getenv('DEBUG', 'False').strip().lower() in ('1', 'true', 'yes')
APPEND_SLASH = False

# POS: the biggest discount (as % of the sale) a CASHIER may give without a
# manager. Owners and managers are not limited. Over-limit offline sales are
# still recorded (the goods are gone) but flagged for review.
CASHIER_MAX_DISCOUNT_PERCENT = int(os.getenv('CASHIER_MAX_DISCOUNT_PERCENT', '10'))

# pytest / `manage.py test` import this module with whatever DEBUG the shell
# happens to have; the secure-by-default DEBUG above must not make the test
# suite explode or 301-redirect every request to https.
_RUNNING_TESTS = 'pytest' in sys.modules or (len(sys.argv) > 1 and sys.argv[1] == 'test')

_INSECURE_DEFAULT_SECRET_KEY = 'django-insecure-vendoriq-change-this-in-production-xyz'
if not DEBUG and not _RUNNING_TESTS and SECRET_KEY == _INSECURE_DEFAULT_SECRET_KEY:
    # Fails loudly at startup rather than silently serving traffic with a
    # SECRET_KEY that's sitting in plain text in this exact source file
    # (public in the repo, and in every export of this codebase). This is
    # not just generic Django hygiene: SIMPLE_JWT below has no SIGNING_KEY
    # override, so django-rest-framework-simplejwt signs every access/
    # refresh token with THIS SAME value by default - anyone who reads it
    # here can forge a valid JWT for any user_id, including staff/
    # superuser accounts, with no password needed at all. render.yaml's
    # `generateValue: true` for SECRET_KEY means the documented Render
    # deploy path already avoids this, but nothing at the code level
    # stopped ANY other deploy path (a quick Railway/Fly.io setup, a raw
    # VPS, a teammate's local "production-like" test) from silently
    # inheriting this default - which is exactly the gap this check closes.
    # DEBUG=True (local dev) is intentionally exempt: using the placeholder
    # key while developing locally is fine and expected.
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        'SECRET_KEY is still the insecure placeholder value while DEBUG=False. '
        'Set a real, random SECRET_KEY before running with DEBUG off - '
        'see .env.example and render.yaml (generateValue: true).'
    )

# Render gives your service a *.onrender.com hostname automatically. RENDER_EXTERNAL_HOSTNAME
# is injected by Render at runtime, so this works without hardcoding your app's URL.
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
RENDER_EXTERNAL_HOSTNAME = os.getenv('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    'unfold',  # must come before django.contrib.admin - replaces its templates with a modern Tailwind-based UI
    'unfold.contrib.filters',  # nicer dropdown/range filter widgets in list views
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # required by allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'dj_rest_auth',
    'rest_framework',
    'rest_framework.authtoken',  # dj_rest_auth's TokenModel requires this app to be installed, even though this project authenticates with JWT, not DRF tokens
    'corsheaders',
    'apps.authentication',
    'apps.stores',
    'apps.products',
    'apps.sales',
    'apps.invoices',
    'apps.staff',
    'apps.insights',
    'apps.ai',
    'apps.expenses',
    'apps.billing',
    'apps.referrals',
    'apps.notifications',
    'apps.customers',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'vendoriq.middleware.MaxBodySizeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Serves collected static files (Django admin CSS/JS) directly from the app -
    # Render doesn't run a separate static file server, so whitenoise fills that gap.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',  # required by allauth since 0.56 - it errors on startup without this
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'vendoriq.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'vendoriq.wsgi.application'

# --- Database -------------------------------------------------------------
# Uses SQLite by default (local dev only). Set DATABASE_URL to point at Supabase
# Postgres in every real deployment - SQLite cannot handle concurrent writes from
# multiple users and must never be used in production.
#
# On Render, put Supabase's *Session pooler* or *Transaction pooler* connection
# string (Project Settings -> Database -> Connection pooling, port 6543) in
# DATABASE_URL, not the direct connection (port 5432). Supabase's direct
# connection has a small hard limit on simultaneous connections; the pooler is
# built to absorb many short-lived connections from an app server, which is
# exactly the shape of traffic a Django + gunicorn deployment produces.
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=int(os.getenv('DB_CONN_MAX_AGE', '0')),
            ssl_require=os.getenv('DB_SSL_REQUIRE', 'True') == 'True',
        )
    }
    # Supabase's pooler runs in "transaction" mode by default, which does not
    # support server-side cursors/prepared statements the way a direct
    # connection does. DISABLE_SERVER_SIDE_CURSORS avoids subtle, hard-to-
    # reproduce errors under load when using the pooler. Harmless if you're
    # using the direct connection instead.
    DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_USER_MODEL = 'authentication.User'

# --- Google sign-in (django-allauth) -----------------------------------------
# Existing email/password login (apps/authentication/views.py) is untouched -
# this only adds Google as an *additional* way in, via
# /api/auth/social/google/ (apps/authentication/social_views.py), which
# returns the same {token, refresh, user} shape as the existing login
# endpoint so the frontend doesn't need two different response handlers.
#
# allauth requires the sites framework even though this project has no
# multi-site concept - SITE_ID=1 is just satisfying that requirement.
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# This User model has no `username` field (email is USERNAME_FIELD) - these
# three lines are what make allauth work with that instead of assuming a
# traditional username exists. Settings API as of allauth 65.4+ - older
# tutorials reference ACCOUNT_AUTHENTICATION_METHOD/ACCOUNT_EMAIL_REQUIRED,
# both deprecated in favor of these.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']

# Registration/login already exists via the app's own email+password flow
# (RegisterView/LoginView) - allauth's own signup/login *views* and email
# verification are not used, only its social-account plumbing, so this
# skips a confirmation-email step that doesn't apply to Google sign-in
# (Google already verified that email address).
ACCOUNT_EMAIL_VERIFICATION = 'none'

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = 'apps.authentication.adapters.SocialAccountAdapter'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        # Credentials come from env vars, not the SocialApp admin model -
        # keeps this consistent with how every other secret in this project
        # is configured (.env locally, Render dashboard in production), and
        # means there's nothing to click through in /admin/ to set this up.
        'APP': {
            'client_id': os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),
            'secret': os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', ''),
            'key': '',
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    # Blocks the ~20,000 most common leaked/guessable passwords (e.g.
    # "Password1", "Qwerty123") - these pass the serializer's own
    # uppercase+digit+length checks but are the first thing any real
    # attacker tries. Actually enforced now - see
    # apps/authentication/serializers.py::RegisterSerializer.validate_password,
    # which calls Django's validate_password() (previously imported but
    # never called, so this validator list was silently having zero effect
    # on registration at all).
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']  # picks up static/branding/logo.png for the admin (see UNFOLD below)
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# --- Product photos: S3-compatible object storage (Supabase Storage, AWS S3,
# Cloudflare R2...). Set MEDIA_S3_BUCKET to switch it on; leave it empty for
# local development, where photos go to ./media. See .env.example.
MEDIA_S3_BUCKET = os.getenv('MEDIA_S3_BUCKET', '')
if MEDIA_S3_BUCKET:
    import importlib.util
    if importlib.util.find_spec('storages') is None:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured('MEDIA_S3_BUCKET is set but django-storages is not installed (pip install "django-storages[s3]").')
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': MEDIA_S3_BUCKET,
            'endpoint_url': os.getenv('MEDIA_S3_ENDPOINT_URL') or None,
            'access_key': os.getenv('MEDIA_S3_ACCESS_KEY_ID', ''),
            'secret_key': os.getenv('MEDIA_S3_SECRET_ACCESS_KEY', ''),
            'region_name': os.getenv('MEDIA_S3_REGION', 'auto'),
            # Public URL base, e.g. <project>.supabase.co/storage/v1/object/public/<bucket>
            'custom_domain': os.getenv('MEDIA_S3_CUSTOM_DOMAIN') or None,
            'addressing_style': 'path',
            'signature_version': 's3v4',
            'querystring_auth': False,      # photos are public product pictures
            'default_acl': None,
            'file_overwrite': False,
            # File names are random, so a stored photo never changes: cache it forever.
            'object_parameters': {'CacheControl': 'public, max-age=31536000, immutable'},
        },
    }

# Hard cap on an incoming product photo. The web app shrinks pictures first (a
# phone photo becomes ~100-300 KB), so this only ever stops oversized direct API uploads.
PRODUCT_PHOTO_MAX_UPLOAD_BYTES = int(os.getenv('PRODUCT_PHOTO_MAX_UPLOAD_BYTES', str(1024 * 1024)))

# Product photo uploads. NOTE: Render's default filesystem is ephemeral -
# files written here disappear on the next deploy/restart. Fine for local
# dev; for production, mount a persistent disk (Render) or swap this for
# object storage (e.g. S3/Cloudinary via django-storages) before relying on
# photos surviving a deploy.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Django's own DEFAULT here is 2.5MB (DATA_UPLOAD_MAX_MEMORY_SIZE) - well
# below the 5MB product photo limit this app actually advertises and
# enforces itself (see ProductsPage.jsx's own 5MB check, and
# apps/products/serializers.py::ProductSerializer.validate_photo, which
# has the matching backend check). Without raising this, any photo between
# 2.5MB and 5MB would be rejected by Django's request parser BEFORE that
# serializer validation ever runs - as a raw, generic Django-level 400
# (SuspiciousOperation -> RequestDataTooBig), not the app's own clean
# "Image must be under 5MB" JSON error - so the frontend would show a
# confusing generic failure instead of either succeeding (as the 5MB limit
# implies it should) or failing with the intended message. Set comfortably
# above 5MB to leave headroom for the rest of a multipart request (the
# other product form fields alongside the photo).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # JWTAuthentication + a password-fingerprint check, so changing a
        # password invalidates every token issued before it.
        'apps.authentication.authentication.PasswordVersionJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'EXCEPTION_HANDLER': 'vendoriq.utils.custom_exception_handler',
    # Rate limiting protects the API (and the database behind it) from being
    # overwhelmed by a traffic spike or a runaway client - without this, a
    # burst of requests from even a handful of misbehaving clients can degrade
    # the service for everyone else.
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': os.getenv('THROTTLE_RATE_ANON', '30/min'),
        'user': os.getenv('THROTTLE_RATE_USER', '300/min'),
        # Endpoints that cost real money or can be abused to spam third
        # parties get their own, much tighter per-user limit.
        'ai_chat': os.getenv('THROTTLE_RATE_AI_CHAT', '20/min'),
        'invoice_send': os.getenv('THROTTLE_RATE_INVOICE_SEND', '30/hour'),
        'verify_send': os.getenv('THROTTLE_RATE_VERIFY_SEND', '10/hour'),
        'verify_confirm': os.getenv('THROTTLE_RATE_VERIFY_CONFIRM', '30/hour'),
        'staff_add': os.getenv('THROTTLE_RATE_STAFF_ADD', '20/hour'),
        'backup': os.getenv('THROTTLE_RATE_BACKUP', '6/hour'),
    },
    # How many reverse proxies sit in front of the app (Render = 1). Without
    # this DRF keys the anon throttle on the WHOLE X-Forwarded-For header,
    # which a client controls - rotating it bypasses every rate limit.
    'NUM_PROXIES': int(os.getenv('NUM_PROXIES', '1')),
}

# --- Login lockout ------------------------------------------------------
# AnonRateThrottle above (30/min per IP) is a generic anti-abuse limit, not
# purpose-built brute-force protection - it's easily worked around by
# rotating IPs, and doesn't stop a determined attacker from grinding
# through a password list against one specific account. This is a second,
# targeted layer: temporarily block further login attempts against a given
# EMAIL (not IP) once it's racked up too many recent failures, regardless
# of which IP they're coming from. See apps/authentication/views.py::LoginView.
#
# Deliberately a TEMPORARY, self-healing window rather than a permanent
# lockout requiring an admin/support unlock: a permanent lockout is itself
# a denial-of-service vector (anyone who knows a victim's email can lock
# them out of their own account indefinitely just by failing their
# password a few times) - OWASP's guidance is temporary lockout with
# backoff for exactly this reason. Built on the EXISTING LoginEvent
# history (already indexed on email_attempted+created_at) rather than a
# new counter field, so there's nothing that can drift out of sync with
# what actually happened.
LOGIN_LOCKOUT_MAX_ATTEMPTS = int(os.getenv('LOGIN_LOCKOUT_MAX_ATTEMPTS', '5'))
LOGIN_LOCKOUT_WINDOW_MINUTES = int(os.getenv('LOGIN_LOCKOUT_WINDOW_MINUTES', '15'))

SIMPLE_JWT = {
    # Short-lived access token + long-lived refresh token (the frontend
    # swaps them automatically - see src/lib/api.js). A stolen access token
    # is useful for an hour, not a week.
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('ACCESS_TOKEN_MINUTES', '60'))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# --- CORS -------------------------------------------------------------------
# CORS_ALLOWED_ORIGINS: exact origins, e.g. your production Vercel domain.
# CORS_ALLOWED_ORIGIN_REGEXES: lets every Vercel *preview* deployment
# (https://vendoriq-<hash>-<team>.vercel.app) through too, without having to
# add a new exact origin every time a preview URL is generated.
CORS_ALLOWED_ORIGINS = [o for o in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if o]

# The deployed frontend's public URL (no trailing slash), e.g.
# https://preciousogbonnaya.vercel.app - used to build absolute links/asset
# URLs (like the logo) in emails, which - unlike in-app pages - cannot use
# relative paths. Defaults to the first CORS origin, which in most
# single-frontend deployments already IS the frontend URL.
FRONTEND_URL = os.getenv('FRONTEND_URL', '').rstrip('/') or (CORS_ALLOWED_ORIGINS[0].rstrip('/') if CORS_ALLOWED_ORIGINS else '')
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://.*\.vercel\.app$',
] if os.getenv('CORS_ALLOW_VERCEL_PREVIEWS', 'True') == 'True' else []
# Worth knowing: *.vercel.app is a shared public hosting namespace - this regex trusts EVERY app
# deployed there, not just yours, since anyone can spin up their own free *.vercel.app site. That is
# acceptable only while CORS_ALLOW_CREDENTIALS is off (the default, same-origin hosting shape): then no
# other origin can make cookie-carrying requests, and the Bearer access token lives in page memory,
# unreachable from another origin. As soon as credentialed CORS is switched on this wildcard is dropped
# automatically (see below) and only the exact CORS_ALLOWED_ORIGINS are trusted. Set
# CORS_ALLOW_VERCEL_PREVIEWS=False to drop it in every case.
# --- Session cookie (HttpOnly refresh token) -------------------------------------
# The refresh token is kept in an HttpOnly cookie that scripts cannot read; only the
# short-lived access token is ever visible to page JavaScript (see apps/authentication/cookies.py).
#
# Two supported hosting shapes:
#   A) SAME-ORIGIN (default, recommended): the web app proxies /api to this server (a Vercel
#      rewrite in vercel.json), so the browser only ever talks to one origin. No CORS is involved
#      and the cookie is a plain first-party cookie. Leave CORS_ALLOW_CREDENTIALS off.
#   B) SAME-SITE custom domains (app.example.com + api.example.com): needs
#      CORS_ALLOW_CREDENTIALS=True so the browser may send the cookie, and the frontend's
#      VITE_API_URL pointing at the API.
# A cookie that must travel between UNRELATED sites (SameSite=None) is blocked by modern
# browsers' third-party-cookie rules, so that shape is not supported.
AUTH_COOKIE_NAME = 'viq_refresh'
AUTH_COOKIE_PATH = '/api/auth/'          # only auth endpoints ever receive it
AUTH_COOKIE_SAMESITE = os.getenv('AUTH_COOKIE_SAMESITE', 'Lax')
AUTH_COOKIE_DOMAIN = os.getenv('AUTH_COOKIE_DOMAIN') or None
AUTH_COOKIE_SECURE = (not DEBUG) if os.getenv('AUTH_COOKIE_SECURE') is None else os.getenv('AUTH_COOKIE_SECURE') == 'True'
# Sessions created BEFORE cookies existed keep their refresh token in localStorage; accepting it once
# in the request body lets the app move it into the cookie without logging anyone out. Switch off
# (AUTH_ALLOW_BODY_REFRESH=False) after 30 days, when every old token has expired anyway.
AUTH_ALLOW_BODY_REFRESH = os.getenv('AUTH_ALLOW_BODY_REFRESH', 'True') == 'True'

CORS_ALLOW_CREDENTIALS = os.getenv('CORS_ALLOW_CREDENTIALS', 'False') == 'True'
if CORS_ALLOW_CREDENTIALS:
    # With credentials a wildcard is dangerous: ANY *.vercel.app site could then make
    # cookie-carrying requests to this API. Credentialed CORS trusts exact origins only.
    CORS_ALLOWED_ORIGIN_REGEXES = []
if AUTH_COOKIE_SAMESITE not in ('Lax', 'Strict'):
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("AUTH_COOKIE_SAMESITE must be 'Lax' or 'Strict' (SameSite=None cookies are blocked as third-party cookies).")
# Browsers hide response headers from cross-origin pages unless exposed - without
# this the backup download couldn't read its filename from Content-Disposition.
CORS_EXPOSE_HEADERS = ['Content-Disposition']

# --- Product analytics (PostHog) ---------------------------------------------------------------
# Server-side events (sign-up, verification, trial, purchase) - see vendoriq/analytics.py. Empty key = off.
# Use the same project API key (phc_...) as the frontend's VITE_POSTHOG_KEY. EU project: set
# POSTHOG_HOST=https://eu.i.posthog.com.
POSTHOG_API_KEY = os.getenv('POSTHOG_API_KEY', '').strip()
POSTHOG_HOST = os.getenv('POSTHOG_HOST', 'https://us.i.posthog.com').strip()

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
# The specific model used for the AI Business Assistant (apps/ai/views.py).
# Groq deprecates/retires models fairly often (see
# https://console.groq.com/docs/deprecations) - keeping this as an env var
# instead of a hardcoded constant means swapping to a replacement model is
# a config change, not a code change/redeploy. Current default is Groq's
# recommended general-purpose flagship as of this writing; verify against
# the deprecations page above before assuming it's still current.
GROQ_MODEL = os.getenv('GROQ_MODEL') or 'openai/gpt-oss-120b'
# Only needed if the "AI provider & model" admin page (apps/ai/models.py)
# is switched to the OpenAI provider instead of Groq.
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# --- Payments (Paystack) -----------------------------------------------------
# Test-mode keys from https://dashboard.paystack.com/#/settings/developer
# (sk_test_... / pk_test_...) - see apps/billing/views.py for the
# initialize/verify flow. Leave both blank to keep the old no-payment mock
# upgrade flow (UpgradeView) as a fallback.
# .strip(): a key pasted into a dashboard usually carries a trailing newline/space, which makes the
# Authorization header invalid and every payment call fail with an unhelpful error.
PAYSTACK_SECRET_KEY = os.getenv('PAYSTACK_SECRET_KEY', '').strip()
PAYSTACK_PUBLIC_KEY = os.getenv('PAYSTACK_PUBLIC_KEY', '').strip()


def _paystack_mode(key):
    return 'live' if '_live_' in key else 'test' if '_test_' in key else None


# A TEST secret key with a LIVE public key (or vice versa) passes every "is it set" check, then the
# checkout popup opens against the wrong environment and real payments fail or never reach this server.
if PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY and not _RUNNING_TESTS:
    if _paystack_mode(PAYSTACK_SECRET_KEY) and _paystack_mode(PAYSTACK_PUBLIC_KEY) and _paystack_mode(PAYSTACK_SECRET_KEY) != _paystack_mode(PAYSTACK_PUBLIC_KEY):
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            'PAYSTACK_SECRET_KEY and PAYSTACK_PUBLIC_KEY are from different Paystack modes '
            '(one is test, one is live). Use the matching pair from the same dashboard mode.'
        )
# The free "demo upgrade" (POST /api/billing/upgrade/) grants Pro with NO
# payment. It exists only so local development works without Paystack keys,
# so it is OFF unless explicitly switched on with ALLOW_MOCK_UPGRADE=true.
# It used to be reachable whenever the Paystack keys happened to be missing
# or incomplete - which on a real deployment meant "anyone can click
# Upgrade and get Pro for free" instead of a clear "payments unavailable".
ALLOW_MOCK_UPGRADE = os.getenv('ALLOW_MOCK_UPGRADE', '').strip().lower() in ('1', 'true', 'yes')

# Email (used to send invoices to customers).
# If EMAIL_HOST is not set, emails print to the console instead of failing,
# so "Send invoice" still works out of the box in local development.
if os.getenv('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@vendoriq.app')
# Verification codes are sent inside the request, so a dead SMTP server must
# fail fast instead of hanging a worker.
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '10'))

# --- SMS (phone verification) ---
# Termii is the default provider for Nigerian numbers. With no API key the
# 'console' backend just logs the message (development only - it is refused
# when DEBUG is off, see apps/authentication/sms.py).
TERMII_API_KEY = os.getenv('TERMII_API_KEY', '')
TERMII_SENDER_ID = os.getenv('TERMII_SENDER_ID', 'N-Alert')
TERMII_CHANNEL = os.getenv('TERMII_CHANNEL', 'dnd')  # 'dnd' also reaches numbers with promo-SMS blocking; 'generic' is cheaper
SMS_BACKEND = os.getenv('SMS_BACKEND') or ('termii' if TERMII_API_KEY else 'console')

# --- Caching -----------------------------------------------------------------
# Cuts repeated database aggregation (dashboard/insights) under concurrent load.
# Defaults to a local in-memory cache (works out of the box, no extra service
# to run) - set REDIS_URL (e.g. Render's Redis add-on, or Upstash) to share one
# cache across every gunicorn worker/dyno for a real multi-instance deployment,
# which is what actually lets this scale to many concurrent users: without a
# shared cache, every worker/dyno recomputes the same dashboard aggregation
# independently on every request.
REDIS_URL = os.getenv('REDIS_URL', '').strip()
if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                # A Redis outage/blip should degrade to "no cache" (fall
                # through to the database), not a 500 for every user -
                # this is what "ensure there is no error" buys us here.
                'IGNORE_EXCEPTIONS': True,
                'CONNECTION_POOL_KWARGS': {'max_connections': 50},
                'SOCKET_CONNECT_TIMEOUT': 3,
                'SOCKET_TIMEOUT': 3,
            },
        }
    }
    DJANGO_REDIS_IGNORE_EXCEPTIONS = True
    DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }

# --- Background tasks (Celery) ------------------------------------------------
# Sending invoice emails synchronously inside the request tied up a gunicorn
# worker/thread for however long the SMTP round-trip took - a slow email
# provider directly ate into the app's request-handling capacity. This
# offloads that (and any future slow, non-interactive work) to a separate
# worker process instead.
#
# CELERY_TASK_ALWAYS_EAGER: with no REDIS_URL (plain local dev), there's no
# broker to hand work off to - rather than requiring everyone to also run a
# `celery worker` process just to develop locally, tasks run inline,
# synchronously, in the request itself. Functionally identical to before
# Celery existed; the async behavior only kicks in once REDIS_URL is set
# (which is true in every real deployment, since Redis is also the cache).
CELERY_BROKER_URL = REDIS_URL or 'memory://'
CELERY_RESULT_BACKEND = REDIS_URL or None
CELERY_TASK_ALWAYS_EAGER = not REDIS_URL
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# Don't let a stuck email provider hang a worker indefinitely.
CELERY_TASK_SOFT_TIME_LIMIT = 25
CELERY_TASK_TIME_LIMIT = 30

# --- Production security hardening ------------------------------------------
# Render terminates TLS at its own proxy and forwards plain HTTP internally,
# so Django needs to be told to trust the X-Forwarded-Proto header - otherwise
# it can't tell a request was actually served over HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True' and not _RUNNING_TESTS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 7  # 1 week; raise once you're confident everything is HTTPS-only
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# --- Logging ------------------------------------------------------------------
# Without this, Django's default logging config only reports 500s by emailing
# ADMINS (which nothing here configures) - meaning any unhandled exception
# under load would fail silently with no trace anywhere. This sends request
# errors and warnings to stdout/stderr, which Render (and `gunicorn`
# generally) captures into the service's log stream automatically, so a
# spike in 500s under a load test is actually visible instead of invisible.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[{levelname}] {asctime} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {
        # Full tracebacks for unhandled view exceptions (500s).
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        # Suspicious-operation / disallowed-host reports. The first LOGGING
        # dict that used to live above this one configured this logger, but
        # the second assignment silently replaced it, so these were lost.
        'django.security': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        # Cache/DB backend warnings (e.g. our own safe_cache_get/set fallbacks).
        'vendoriq': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'django_redis': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
}

# --- Admin UI (django-unfold) --------------------------------------------------
# Branded to match the app's own green palette (see vendoriq-frontend's
# tailwind.config.js brand.* scale) rather than Unfold's default blue, so the
# admin doesn't look like an unrelated product bolted onto VendorIQ.
UNFOLD = {
    'SITE_TITLE': 'VendorIQ Admin',
    'SITE_HEADER': 'VendorIQ',
    'SITE_SYMBOL': 'storefront',
    # The real logo (same asset as the frontend's /icons/logo.png -
    # vendoriq-frontend/public/icons/logo.png) instead of a generic Material
    # icon. SITE_SYMBOL above is kept as the fallback used in a couple of
    # places Unfold doesn't accept an image (e.g. the browser tab favicon).
    'SITE_ICON': lambda request: static('branding/logo.png'),
    'SITE_LOGO': lambda request: static('branding/logo.png'),
    'SHOW_HISTORY': True,
    'SHOW_VIEW_ON_SITE': False,
    'DASHBOARD_CALLBACK': 'vendoriq.admin_dashboard.dashboard_callback',
    'COLORS': {
        'primary': {
            '50': '234 247 239',
            '100': '198 235 213',
            '200': '162 219 185',
            '300': '120 199 154',
            '400': '52 168 112',
            '500': '30 132 73',
            '600': '22 112 60',
            '700': '18 92 49',
            '800': '15 74 40',
            '900': '11 56 30',
            '950': '6 34 18',
        },
    },
    'SIDEBAR': {
        'show_search': True,
        'show_all_applications': False,  # navigation below replaces the default per-app listing
        'navigation': [
            {
                'title': _('Platform'),
                'separator': True,
                'items': [
                    {'title': _('Dashboard'), 'icon': 'dashboard', 'link': reverse_lazy('admin:index')},
                    {'title': _('Analytics'), 'icon': 'monitoring', 'link': '/admin/#analytics'},
                ],
            },
            {
                'title': _('Entities'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('Tenants (Stores)'), 'icon': 'storefront', 'link': reverse_lazy('admin:stores_store_changelist')},
                    {'title': _('Users'), 'icon': 'group', 'link': reverse_lazy('admin:authentication_user_changelist')},
                    {'title': _('Staff roles'), 'icon': 'badge', 'link': reverse_lazy('admin:stores_staff_changelist')},
                    {'title': _('Products'), 'icon': 'inventory_2', 'link': reverse_lazy('admin:products_product_changelist')},
                    {'title': _('Sales'), 'icon': 'point_of_sale', 'link': reverse_lazy('admin:sales_sale_changelist')},
                    {'title': _('Invoices'), 'icon': 'receipt_long', 'link': reverse_lazy('admin:invoices_invoice_changelist')},
                    {'title': _('Expenses'), 'icon': 'payments', 'link': reverse_lazy('admin:expenses_expense_changelist')},
                ],
            },
            {
                'title': _('Revenue & Billing'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('Revenue'), 'icon': 'payments', 'link': reverse_lazy('admin_revenue')},
                    {'title': _('Subscriptions'), 'icon': 'workspace_premium', 'link': reverse_lazy('admin:billing_subscription_changelist')},
                    {'title': _('Subscription purchases'), 'icon': 'receipt_long', 'link': reverse_lazy('admin:billing_subscriptionpurchase_changelist')},
                    {'title': _('Plan prices'), 'icon': 'sell', 'link': reverse_lazy('admin:billing_planprice_changelist')},
                    {'title': _('Free trial length'), 'icon': 'hourglass_top', 'link': reverse_lazy('admin:billing_trialsettings_changelist')},
                    {'title': _('Plans & Settings'), 'icon': 'tune', 'link': reverse_lazy('admin_plan_settings')},
                ],
            },
            {
                'title': _('Security'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('Audit logs (login/device history)'), 'icon': 'history', 'link': reverse_lazy('admin:authentication_loginevent_changelist')},
                ],
            },
            {
                'title': _('AI'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('AI usage & conversations'), 'icon': 'insights', 'link': reverse_lazy('admin_ai_usage')},
                    {'title': _('AI provider & model'), 'icon': 'tune', 'link': reverse_lazy('admin:ai_aisettings_changelist')},
                    {'title': _('Raw AI messages'), 'icon': 'smart_toy', 'link': reverse_lazy('admin:ai_chatmessage_changelist')},
                ],
            },
            {
                'title': _('Referrals'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('Referral settings'), 'icon': 'tune', 'link': reverse_lazy('admin:referrals_referralsettings_changelist')},
                    {'title': _('Referrals'), 'icon': 'group_add', 'link': reverse_lazy('admin:referrals_referral_changelist')},
                    {'title': _('Commissions'), 'icon': 'payments', 'link': reverse_lazy('admin:referrals_referralcommission_changelist')},
                    {'title': _('Payout accounts'), 'icon': 'account_balance', 'link': reverse_lazy('admin:referrals_payoutaccount_changelist')},
                ],
            },
            {
                'title': _('System'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('System health'), 'icon': 'monitor_heart', 'link': reverse_lazy('admin_system_health')},
                    {'title': _('Support'), 'icon': 'support_agent', 'link': reverse_lazy('admin_support')},
                ],
            },
            {
                'title': _('Notifications'),
                'separator': True,
                'collapsible': True,
                'items': [
                    {'title': _('Send notification to all users'), 'icon': 'campaign', 'link': reverse_lazy('admin:notifications_announcement_add')},
                    {'title': _('Announcements'), 'icon': 'notifications', 'link': reverse_lazy('admin:notifications_announcement_changelist')},
                    {'title': _('Reminders sent to users'), 'icon': 'notification_important', 'link': reverse_lazy('admin:notifications_notification_changelist')},
                ],
            },
        ],
    },
}

# --- Error monitoring (Sentry) ------------------------------------------------
# Without this, an unhandled exception in production is only visible if
# someone happens to be tailing Render's logs when it happens (see the
# LOGGING config above, which sends errors to stdout - necessary but not
# sufficient: nothing pages anyone). Sentry catches it immediately and
# tells you what broke, for whom, and how often.
#
# Entirely opt-in: no SENTRY_DSN set (the default, including in every test
# run and local dev by default) means this block does nothing at all - no
# package failure, no accidental reporting, nothing sent anywhere.
SENTRY_DSN = os.getenv('SENTRY_DSN', '').strip()
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),  # catches failures in the invoice-email background task too, not just web requests
            RedisIntegration(),
            # Mirrors this project's own LOGGING config (see above): anything
            # logged at ERROR or above (e.g. the vendoriq.cache_utils warnings,
            # the AI view's Groq-failure logging) also becomes a Sentry event,
            # not just a console line.
            LoggingIntegration(level=None, event_level='ERROR'),
        ],
        environment=os.getenv('SENTRY_ENVIRONMENT', 'production' if not DEBUG else 'development'),
        # Performance tracing costs quota on Sentry's free tier - sampled low
        # rather than off, so there's still some visibility into slow
        # requests without burning through the monthly limit on a small app.
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
        # Off by default: request/user data (IPs, headers, etc) is not sent
        # unless explicitly turned on - errs toward not leaking customer
        # data (this app handles real names/emails/phone numbers) into a
        # third-party tool by default.
        send_default_pii=os.getenv('SENTRY_SEND_PII', 'False') == 'True',
    )
