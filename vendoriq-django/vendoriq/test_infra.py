"""Neon + Cloudflare R2 configuration rules (pure functions, no database needed)."""
import pytest

from vendoriq import infra

ACCOUNT = 'a' * 32
POOLED = 'postgresql://u:p@ep-cool-123-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
DIRECT = 'postgresql://u:p@ep-cool-123.eu-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require'


def r2_env(**override):
    env = {'R2_ACCOUNT_ID': ACCOUNT, 'R2_BUCKET': 'vendoriq-photos', 'R2_ACCESS_KEY_ID': 'k' * 32,
           'R2_SECRET_ACCESS_KEY': 's' * 64, 'R2_PUBLIC_URL': 'https://photos.vendoriq.app/'}
    env.update(override)
    return env


class TestNeonConnections:
    def test_pooled_and_direct_hosts_are_told_apart(self):
        assert infra.is_neon_pooled(POOLED) and not infra.is_neon_pooled(DIRECT)
        assert infra.is_neon(DIRECT) and not infra.is_neon('postgresql://u:p@db.example.com/x')

    def test_the_running_app_uses_the_pooled_url(self):
        env = {'DATABASE_URL': POOLED, 'DATABASE_URL_DIRECT': DIRECT}
        for argv in (['gunicorn'], ['manage.py', 'runserver'], ['-A', 'vendoriq', 'worker'], ['manage.py', 'check_live_config']):
            assert infra.pick_database_url(env, argv) == (POOLED, 'default')

    def test_schema_commands_use_the_direct_url(self):
        env = {'DATABASE_URL': POOLED, 'DATABASE_URL_DIRECT': DIRECT}
        for command in ('migrate', 'makemigrations', 'showmigrations', 'sqlmigrate', 'dbshell'):
            assert infra.pick_database_url(env, ['manage.py', command]) == (DIRECT, 'direct')

    def test_without_a_direct_url_everything_uses_database_url(self):
        assert infra.pick_database_url({'DATABASE_URL': POOLED}, ['manage.py', 'migrate']) == (POOLED, 'default')

    def test_nothing_set_means_sqlite_for_local_development(self):
        assert infra.pick_database_url({}, ['manage.py', 'runserver']) == ('', 'default')

    def test_warnings(self):
        assert any('DIRECT connection' in w for w in infra.database_warnings({'DATABASE_URL': DIRECT}, ['x']))
        assert any('DATABASE_URL_DIRECT' in w for w in infra.database_warnings({'DATABASE_URL': POOLED}, ['manage.py', 'migrate']))
        assert any('POOLED host' in w for w in infra.database_warnings({'DATABASE_URL': POOLED, 'DATABASE_URL_DIRECT': POOLED}, ['x']))
        assert infra.database_warnings({'DATABASE_URL': POOLED, 'DATABASE_URL_DIRECT': DIRECT}, ['manage.py', 'migrate']) == []


class TestR2Storage:
    def test_not_configured_is_none(self):
        assert infra.r2_storage_options({}) is None

    def test_builds_the_options_for_django_storages(self):
        o = infra.r2_storage_options(r2_env())
        assert o['endpoint_url'] == f'https://{ACCOUNT}.r2.cloudflarestorage.com'
        assert o['bucket_name'] == 'vendoriq-photos' and o['region_name'] == 'auto'
        assert o['custom_domain'] == 'photos.vendoriq.app'          # scheme and trailing slash removed
        assert o['querystring_auth'] is False and o['default_acl'] is None and o['signature_version'] == 's3v4'
        assert o['file_overwrite'] is False

    def test_eu_jurisdiction_changes_the_endpoint(self):
        assert infra.r2_storage_options(r2_env(R2_JURISDICTION='eu'))['endpoint_url'] == f'https://{ACCOUNT}.eu.r2.cloudflarestorage.com'

    def test_an_explicit_endpoint_wins(self):
        assert infra.r2_storage_options(r2_env(R2_ENDPOINT_URL='https://x.example.com'))['endpoint_url'] == 'https://x.example.com'

    def test_partial_configuration_is_refused_and_names_what_is_missing(self):
        env = r2_env()
        del env['R2_SECRET_ACCESS_KEY']
        with pytest.raises(infra.InfraConfigError, match='R2_SECRET_ACCESS_KEY'):
            infra.r2_storage_options(env)

    def test_account_id_must_be_the_32_char_hex_id(self):
        for bad in ('vendoriq-photos', 'a' * 31, 'g' * 32, ''):
            env = r2_env(R2_ACCOUNT_ID=bad)
            with pytest.raises(infra.InfraConfigError):
                infra.r2_storage_options(env)

    def test_the_private_s3_address_is_not_a_public_url(self):
        with pytest.raises(infra.InfraConfigError, match='PRIVATE'):
            infra.r2_storage_options(r2_env(R2_PUBLIC_URL=f'https://{ACCOUNT}.r2.cloudflarestorage.com/vendoriq-photos'))

    def test_bad_jurisdiction_and_bare_host_values(self):
        with pytest.raises(infra.InfraConfigError):
            infra.r2_storage_options(r2_env(R2_JURISDICTION='mars'))
        assert infra.r2_storage_options(r2_env(R2_PUBLIC_URL='photos.vendoriq.app'))['custom_domain'] == 'photos.vendoriq.app'

    def test_credentials_are_whitespace_stripped(self):
        o = infra.r2_storage_options(r2_env(R2_ACCESS_KEY_ID='  ' + 'k' * 32 + '\n', R2_SECRET_ACCESS_KEY=' ' + 's' * 64 + '\n'))
        assert o['access_key'] == 'k' * 32 and o['secret_key'] == 's' * 64

    def test_r2_dev_addresses_get_a_warning(self):
        assert 'development only' in infra.r2_public_host_warning(r2_env(R2_PUBLIC_URL='https://pub-abc123.r2.dev'))
        assert infra.r2_public_host_warning(r2_env()) == ''
