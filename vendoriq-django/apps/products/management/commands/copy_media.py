"""
python manage.py copy_media --from-url https://old-host/old/public/path  [--dry-run]
python manage.py copy_media --from-dir ./media                            [--dry-run]

One-off: copies every product photo that is recorded in the database into the CURRENT file storage
(Cloudflare R2) under the SAME name, so the database rows keep working. Use it when moving photos from
Supabase Storage (--from-url, its public URL ending in the bucket name) or from a local ./media folder
(--from-dir). Safe to run again: photos already in R2 are skipped.
"""
import os
from urllib.parse import quote

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from apps.products.models import Product


class Command(BaseCommand):
    help = 'Copy existing product photos into the configured file storage (R2), keeping their names.'

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument('--from-url', help='Public base URL the photos are currently served from (name is appended).')
        source.add_argument('--from-dir', help='Local folder holding the photos (e.g. ./media).')
        parser.add_argument('--dry-run', action='store_true', help='Only report what would be copied.')

    def _read(self, opts, name):
        if opts['from_dir']:
            with open(os.path.join(opts['from_dir'], name), 'rb') as fh:
                return fh.read()
        r = requests.get(opts['from_url'].rstrip('/') + '/' + quote(name), timeout=30)
        if r.status_code != 200:
            raise CommandError(f'HTTP {r.status_code}')
        return r.content

    def handle(self, *args, **opts):
        names = [n for n in Product.objects.exclude(photo='').exclude(photo__isnull=True).values_list('photo', flat=True)]
        copied = skipped = failed = 0
        for name in names:
            try:
                if default_storage.exists(name):
                    skipped += 1
                    continue
                if opts['dry_run']:
                    self.stdout.write(f'would copy {name}')
                    copied += 1
                    continue
                saved = default_storage.save(name, ContentFile(self._read(opts, name)))
                if saved != name:      # the row points at `name`; a different stored name would break the photo
                    default_storage.delete(saved)
                    raise CommandError(f'stored as {saved} instead of {name}')
                copied += 1
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f'FAILED {name}: {exc}'))
        verb = 'would copy' if opts['dry_run'] else 'copied'
        self.stdout.write(self.style.SUCCESS(f'{len(names)} photo(s) in the database: {verb} {copied}, already present {skipped}, failed {failed}'))
        if failed:
            raise SystemExit(1)
