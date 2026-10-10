"""
Keep the photo store tidy: one photo per product means a replaced or removed
photo, and the photo of a deleted product, must not linger forever - orphaned
files are exactly how storage costs creep up unnoticed.
"""
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Product


def _delete_file(storage, name):
    if name:
        try:
            storage.delete(name)
        except Exception:  # a storage hiccup must never fail the request that triggered cleanup
            import logging
            logging.getLogger(__name__).warning('Could not delete stored photo %s', name, exc_info=True)


@receiver(pre_save, sender=Product)
def remember_old_photo(sender, instance, update_fields=None, **kwargs):
    # Sales save products with update_fields=['quantity', ...] on every line item;
    # don't add a query to every sale unless the photo could actually be changing.
    if update_fields is not None and 'photo' not in update_fields:
        return
    if instance.pk:
        instance._old_photo_name = Product.objects.filter(pk=instance.pk).values_list('photo', flat=True).first()


@receiver(post_save, sender=Product)
def delete_replaced_photo(sender, instance, update_fields=None, **kwargs):
    old = getattr(instance, '_old_photo_name', None)
    if not old or old == (instance.photo.name or ''):
        return
    storage = instance.photo.storage
    transaction.on_commit(lambda: _delete_file(storage, old))
    instance._old_photo_name = None


@receiver(post_delete, sender=Product)
def delete_photo_of_deleted_product(sender, instance, **kwargs):
    if instance.photo and instance.photo.name:
        storage, name = instance.photo.storage, instance.photo.name
        transaction.on_commit(lambda: _delete_file(storage, name))
