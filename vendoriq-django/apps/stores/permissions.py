from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied, NotFound
from .models import Store, Staff


def get_store_or_404(store_id):
    """
    Existence check ONLY - deliberately takes no `user` argument (an
    earlier version did, and silently ignored it, which is exactly the
    kind of signature that invites a future caller to assume passing
    `user` means this also checks access - it never did). Authorization is
    require_store_access()'s job, always as a separate, explicit call -
    see StoreScopedAPIView.initial() for why that pairing can't be
    accidentally skipped for anything using that base class.
    """
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
