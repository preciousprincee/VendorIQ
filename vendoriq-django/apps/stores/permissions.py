from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, NotFound
from .models import Store, Staff


def get_store_or_404(store_id, user):
    try:
        return Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        raise NotFound('Store not found.')


def get_store_role(store, user):
    if store.owner == user:
        return 'OWNER'
    try:
        staff = Staff.objects.get(store=store, user=user)
        return staff.role
    except Staff.DoesNotExist:
        return None


def require_store_access(store, user, allowed_roles=None):
    role = get_store_role(store, user)
    if role is None:
        raise PermissionDenied('You do not have access to this store.')
    if allowed_roles and role not in allowed_roles:
        raise PermissionDenied('You do not have permission for this action.')
    return role
