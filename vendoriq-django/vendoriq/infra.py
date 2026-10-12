"""
Where the data lives: Neon (PostgreSQL) and Cloudflare R2 (file storage).

Pure functions with no Django imports, so they are easy to test and settings.py stays short.

NEON  (https://neon.com/docs/connect/connection-pooling)
  Neon gives every database TWO connection strings:
    * POOLED  - host contains "-pooler" (PgBouncer, transaction mode). Use it for the running app and
                the Celery worker: it absorbs the many short-lived connections gunicorn creates.
    * DIRECT  - no "-pooler". Use it for schema migrations, pg_dump/pg_restore and anything that relies on
                session state, which transaction pooling does not support.
  So: DATABASE_URL = pooled (runtime); DATABASE_URL_DIRECT = direct (only used by `manage.py migrate` & co).

CLOUDFLARE R2  (https://developers.cloudflare.com/r2/)
  S3-compatible. Private S3 API at https://<ACCOUNT_ID>.r2.cloudflarestorage.com (that is where the app
  WRITES); photos are READ by browsers through a PUBLIC address: a custom domain connected to the bucket
  (recommended) or the bucket's r2.dev address (Cloudflare marks that for development only and rate-limits it).
"""
import re
from urllib.parse import urlparse

# `manage.py` sub-commands that change or inspect the schema: these must not run through PgBouncer.
DIRECT_ONLY_COMMANDS = frozenset({
    'migrate', 'makemigrations', 'showmigrations', 'sqlmigrate', 'squashmigrations', 'dbshell', 'loaddata', 'flush',
})

_ACCOUNT_ID = re.compile(r'^[0-9a-fA-F]{32}$')
R2_JURISDICTIONS = ('', 'eu', 'fedramp')


class InfraConfigError(ValueError):
    """A configuration problem the operator can fix; the message says exactly how."""


# --------------------------------------------------------------------------- database
def host_of(url):
    return (urlparse(url).hostname or '').lower() if url else ''


def is_neon_pooled(url):
    host = host_of(url)
    return host.endswith('.neon.tech') and '-pooler' in host.split('.')[0]


def is_neon(url):
    return host_of(url).endswith('.neon.tech')


def pick_database_url(env, argv):
    """
    -> (url, kind) with kind in {'default', 'direct'}.
    Schema commands use DATABASE_URL_DIRECT when it is set; everything else uses DATABASE_URL.
    """
    url = (env.get('DATABASE_URL') or '').strip()
    direct = (env.get('DATABASE_URL_DIRECT') or '').strip()
    command = argv[1] if len(argv) > 1 else ''
    if direct and command in DIRECT_ONLY_COMMANDS:
        return direct, 'direct'
    return url, 'default'


def database_warnings(env, argv):
    """Human-readable problems worth printing (not fatal)."""
    out = []
    url = (env.get('DATABASE_URL') or '').strip()
    direct = (env.get('DATABASE_URL_DIRECT') or '').strip()
    command = argv[1] if len(argv) > 1 else ''
    if is_neon(url) and not is_neon_pooled(url):
        out.append('DATABASE_URL is a Neon DIRECT connection. For the running app use the POOLED one (host contains "-pooler") '
                   'so many gunicorn workers cannot exhaust Postgres connections.')
    if is_neon_pooled(url) and not direct and command in DIRECT_ONLY_COMMANDS:
        out.append(f'`manage.py {command}` is running through the pooled Neon connection. Neon recommends the DIRECT connection '
                   'for schema work: set DATABASE_URL_DIRECT.')
    if direct and is_neon_pooled(direct):
        out.append('DATABASE_URL_DIRECT points at a POOLED host ("-pooler"). It must be the direct (non-pooled) connection string.')
    return out


# --------------------------------------------------------------------------- R2 file storage
R2_ENV_NAMES = ('R2_ACCOUNT_ID', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_PUBLIC_URL')


def normalize_public_host(value):
    """'https://Photos.Example.com/' -> 'photos.example.com'. Accepts a bare host or a full URL."""
    value = (value or '').strip()
    if not value:
        return ''
    if '://' not in value:
        value = 'https://' + value
    return (urlparse(value).netloc or '').lower()


def r2_endpoint(account_id, jurisdiction=''):
    middle = f'.{jurisdiction}' if jurisdiction else ''
    return f'https://{account_id}{middle}.r2.cloudflarestorage.com'


def r2_configured_names(env):
    return [n for n in R2_ENV_NAMES if (env.get(n) or '').strip()]


def r2_storage_options(env):
    """
    Returns the django-storages S3Storage OPTIONS for R2, or None when no R2_* variable is set.
    Raises InfraConfigError when the configuration is partial or obviously wrong.
    """
    present = r2_configured_names(env)
    if not present:
        return None
    missing = [n for n in R2_ENV_NAMES if n not in present]
    if missing:
        raise InfraConfigError('Cloudflare R2 is only partly configured. Missing: ' + ', '.join(missing) + '.')

    account = env['R2_ACCOUNT_ID'].strip()
    if not _ACCOUNT_ID.match(account):
        raise InfraConfigError('R2_ACCOUNT_ID must be the 32-character hex Account ID from the Cloudflare R2 overview page '
                               '(not the bucket name, a zone ID or the API token).')
    jurisdiction = (env.get('R2_JURISDICTION') or '').strip().lower()
    if jurisdiction not in R2_JURISDICTIONS:
        raise InfraConfigError('R2_JURISDICTION must be empty, "eu" or "fedramp".')

    host = normalize_public_host(env['R2_PUBLIC_URL'])
    if not host or '.' not in host:
        raise InfraConfigError('R2_PUBLIC_URL must be the public address of the bucket, e.g. photos.yourdomain.com.')
    if host.endswith('.r2.cloudflarestorage.com'):
        raise InfraConfigError('R2_PUBLIC_URL is the PRIVATE S3 address. Connect a custom domain to the bucket in the Cloudflare '
                               'dashboard (R2 > bucket > Settings > Public access > Custom Domains) and use that domain.')

    return {
        'bucket_name': env['R2_BUCKET'].strip(),
        'endpoint_url': (env.get('R2_ENDPOINT_URL') or '').strip() or r2_endpoint(account, jurisdiction),
        'access_key': env['R2_ACCESS_KEY_ID'].strip(),
        'secret_key': env['R2_SECRET_ACCESS_KEY'].strip(),
        'region_name': 'auto',               # R2 has no regions; "auto" is what it expects
        'custom_domain': host,               # photos are read from here, not from the S3 endpoint
        'url_protocol': 'https:',
        'addressing_style': 'path',
        'signature_version': 's3v4',
        'querystring_auth': False,           # public product pictures: no per-request signatures in the URL
        'default_acl': None,                 # R2 does not support ACLs
        'file_overwrite': False,             # never silently replace another product's photo
        # File names are random, so a stored photo never changes: cache it forever.
        'object_parameters': {'CacheControl': 'public, max-age=31536000, immutable'},
    }


def r2_public_host_warning(env):
    host = normalize_public_host(env.get('R2_PUBLIC_URL', ''))
    if host.endswith('.r2.dev'):
        return ('R2_PUBLIC_URL is an r2.dev address. Cloudflare provides r2.dev for development only and rate-limits it; '
                'connect a custom domain to the bucket for production.')
    return ''
