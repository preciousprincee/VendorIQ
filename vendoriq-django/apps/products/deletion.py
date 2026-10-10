"""
Product deletion with approval.

A cashier cannot delete a product, but can ask: they give a remark, the request
goes (as a notification) to the store owner and every manager, and the product
is only deleted when one of them approves. Owners and managers still delete
directly (ProductDetailView.delete) - no approval step for people who could
approve it anyway.
"""
import logging

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from apps.stores.models import Staff
from .models import Product, ProductDeletionRequest

logger = logging.getLogger(__name__)

Status = ProductDeletionRequest.Status
MIN_REMARK, MAX_REMARK = 5, 300

HISTORY_MESSAGE = (
    "This product has sales or invoice history and can't be deleted, since that would break those records. "
    'Set its stock to 0 or rename it to "discontinued" instead.'
)


class DeletionError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def has_history(product):
    # Imported here: apps.sales / apps.invoices import this app's models at module level.
    from apps.sales.models import SaleItem
    from apps.invoices.models import InvoiceItem
    return SaleItem.objects.filter(product=product).exists() or InvoiceItem.objects.filter(product=product).exists()


def _clean(text, limit):
    return ' '.join(str(text or '').split())[:limit]


def approvers(store):
    """The people who can approve: the owner and every manager of the store."""
    users = {store.owner_id: store.owner}
    for staff in Staff.objects.filter(store=store, role='MANAGER').select_related('user'):
        users[staff.user_id] = staff.user
    return list(users.values())


def _notify(users, *, kind, title, message, dedupe_key, link, severity='medium'):
    from apps.notifications.models import Notification
    Notification.objects.bulk_create([
        Notification(user=u, kind=kind, severity=severity, title=title[:120], message=message, link=link, dedupe_key=dedupe_key)
        for u in users
    ], ignore_conflicts=True)  # unique (user, dedupe_key): a repeat is a no-op


def _clear_request_notifications(request_id):
    """Once decided, the question is answered - take it off every approver's bell."""
    from apps.notifications.models import Notification
    Notification.objects.filter(dedupe_key=f'deletion-request:{request_id}').delete()


def request_deletion(*, store, user, product, remark):
    remark = _clean(remark, MAX_REMARK + 1)
    if len(remark) < MIN_REMARK:
        raise DeletionError(f'Please explain why this product should be deleted (at least {MIN_REMARK} characters).')
    if len(remark) > MAX_REMARK:
        raise DeletionError(f'Please keep the remark under {MAX_REMARK} characters.')
    # Tell the cashier NOW, rather than sending managers a request that can never be approved.
    if has_history(product):
        raise DeletionError(HISTORY_MESSAGE, 409)

    try:
        with transaction.atomic():
            req = ProductDeletionRequest.objects.create(
                store=store, product=product, product_name=product.name, requested_by=user, remark=remark,
            )
            recipients = [u for u in approvers(store) if u.pk != user.pk]
            _notify(
                recipients, kind='deletion_request', title='Delete product request',
                message=f'{user.name} asked to delete "{product.name}": {remark}',
                dedupe_key=f'deletion-request:{req.id}', link='/products?requests=1',
            )
    except IntegrityError:
        raise DeletionError('A deletion request for this product is already waiting for approval.', 409)
    return req


def _pending_for_update(store, request_id):
    req = ProductDeletionRequest.objects.select_for_update().filter(id=request_id, store=store).first()
    if req is None:
        raise DeletionError('Request not found.', 404)
    if req.status != Status.PENDING:
        raise DeletionError('This request has already been handled.', 409)
    return req


def _finish(req, status, user, note):
    req.status = status
    req.decided_by = user
    req.decided_at = timezone.now()
    req.decision_note = _clean(note, MAX_REMARK)
    req.save(update_fields=['status', 'decided_by', 'decided_at', 'decision_note'])
    _clear_request_notifications(req.id)


def approve(*, store, user, request_id, note=''):
    with transaction.atomic():
        req = _pending_for_update(store, request_id)
        # Load the product AFRESH rather than through `req.product`. Deleting a model
        # instance sets its primary key to None; if that same object were cached on
        # `req`, saving `req` afterwards (in _finish) makes Django refuse with
        # "save() prohibited to prevent data loss due to unsaved related object
        # 'product'" - the whole approval then rolled back with a server error and the
        # product was never deleted.
        product = Product.objects.filter(pk=req.product_id).first() if req.product_id else None
        if product is not None:
            try:
                with transaction.atomic():
                    product.delete()
            except ProtectedError:
                # A sale or invoice was made for it AFTER the request was sent. The
                # request stays pending so the approver can reject it with a reason.
                raise DeletionError(HISTORY_MESSAGE, 409)
        # (product already gone = the outcome the cashier wanted; still record it as approved)
        _finish(req, Status.APPROVED, user, note)
        if req.requested_by_id:
            _notify(
                [req.requested_by], kind='deletion_decision', title='Deletion approved',
                message=f'"{req.product_name}" was deleted (approved by {user.name}).' + (f' Note: {req.decision_note}' if req.decision_note else ''),
                dedupe_key=f'deletion-decision:{req.id}', link='/products', severity='low',
            )
    return req


def delete_directly(product, user):
    """
    An owner or manager deletes a product themselves. If a cashier had already
    asked for it, that request is settled in the same step (it would otherwise sit
    in everyone's review list forever, pointing at a product that no longer exists),
    and the cashier is told. A ProtectedError (sales/invoice history) propagates and
    rolls everything back - the caller turns it into a 409.
    """
    with transaction.atomic():
        pending = list(ProductDeletionRequest.objects.select_for_update().filter(product_id=product.pk, status=Status.PENDING))
        product.delete()
        for req in pending:
            _finish(req, Status.APPROVED, user, f'Deleted directly by {user.name}')
            if req.requested_by_id and req.requested_by_id != user.pk:
                _notify(
                    [req.requested_by], kind='deletion_decision', title='Deletion approved',
                    message=f'"{req.product_name}" was deleted by {user.name}.',
                    dedupe_key=f'deletion-decision:{req.id}', link='/products', severity='low',
                )


def reject(*, store, user, request_id, note=''):
    with transaction.atomic():
        req = _pending_for_update(store, request_id)
        _finish(req, Status.REJECTED, user, note)
        if req.requested_by_id:
            _notify(
                [req.requested_by], kind='deletion_decision', title='Deletion request declined',
                message=f'{user.name} declined your request to delete "{req.product_name}".' + (f' Reason: {req.decision_note}' if req.decision_note else ''),
                dedupe_key=f'deletion-decision:{req.id}', link='/products', severity='low',
            )
    return req


def cancel(*, store, user, request_id):
    with transaction.atomic():
        req = _pending_for_update(store, request_id)
        if req.requested_by_id != user.pk:
            raise DeletionError('You can only cancel your own requests.', 403)
        _finish(req, Status.CANCELLED, user, '')
    return req


def serialize(req):
    return {
        'id': str(req.id),
        'product_id': str(req.product_id) if req.product_id else None,
        'product_name': req.product_name,
        'remark': req.remark,
        'status': req.status,
        'requested_by': str(req.requested_by_id) if req.requested_by_id else None,
        'requested_by_name': req.requested_by.name if req.requested_by_id else 'Former staff member',
        'created_at': req.created_at,
        'decided_by_name': req.decided_by.name if req.decided_by_id else None,
        'decided_at': req.decided_at,
        'decision_note': req.decision_note,
    }
