from django.conf import settings
from django.core.checks import Warning, register


@register()
def photo_storage_is_persistent(app_configs, **kwargs):
    """
    On Render (and most hosts) the local disk is wiped on every deploy, so
    product photos kept there silently vanish. Surfaces in `manage.py check`
    and the migrate step of the build log.
    """
    if settings.DEBUG:
        return []
    backend = settings.STORAGES.get('default', {}).get('BACKEND', '')
    if backend.endswith('FileSystemStorage'):
        return [Warning(
            'Product photos are stored on the server\'s local disk, which is erased on every deploy.',
            hint='Set the R2_* variables (Cloudflare R2 object storage) - see .env.example.',
            id='products.W001',
        )]
    return []
