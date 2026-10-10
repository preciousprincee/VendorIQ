from rest_framework import status
from rest_framework.response import Response

from apps.stores.base_views import StoreScopedAPIView
from vendoriq.cache_utils import invalidate_store_insights
from . import deletion
from .models import Product, ProductDeletionRequest

APPROVER_ROLES = ['OWNER', 'MANAGER']


def _note(request):
    body = request.data if isinstance(request.data, dict) else {}
    value = body.get('note', '')
    return value if isinstance(value, str) else ''


def _err(exc):
    return Response({'error': exc.message}, status=exc.status)


class DeletionRequestCreateView(StoreScopedAPIView):
    """POST /<store>/products/<id>/deletion-request/ {remark} - a cashier asks for a product to be deleted."""
    allowed_roles = None

    def post(self, request, store_id, product_id):
        if self.role in APPROVER_ROLES:
            return Response({'error': 'You can delete this product directly - no request is needed.'}, status=status.HTTP_400_BAD_REQUEST)
        product = Product.objects.filter(id=product_id, store=self.store).first()
        if product is None:
            return Response({'error': 'Product not found.'}, status=status.HTTP_404_NOT_FOUND)
        body = request.data if isinstance(request.data, dict) else {}
        remark = body.get('remark')
        try:
            req = deletion.request_deletion(store=self.store, user=request.user, product=product, remark=remark if isinstance(remark, str) else '')
        except deletion.DeletionError as exc:
            return _err(exc)
        return Response({'request': deletion.serialize(req)}, status=status.HTTP_201_CREATED)


class DeletionRequestListView(StoreScopedAPIView):
    """
    GET /<store>/deletion-requests/?status=PENDING|ALL
    Owners and managers see every request in the store; a cashier sees only
    their own (so the product list can show "deletion pending").
    """
    allowed_roles = None

    def get(self, request, store_id):
        qs = ProductDeletionRequest.objects.filter(store=self.store).select_related('requested_by', 'decided_by')
        if self.role not in APPROVER_ROLES:
            qs = qs.filter(requested_by=request.user)
        if request.query_params.get('status', 'PENDING').upper() != 'ALL':
            qs = qs.filter(status=ProductDeletionRequest.Status.PENDING)
        return Response({'requests': [deletion.serialize(r) for r in qs[:100]]})


class _Decision(StoreScopedAPIView):
    def finish(self, store_id, fn, **kwargs):
        try:
            req = fn(store=self.store, **kwargs)
        except deletion.DeletionError as exc:
            return _err(exc)
        invalidate_store_insights(store_id)
        req = ProductDeletionRequest.objects.select_related('requested_by', 'decided_by').get(pk=req.pk)
        return Response({'request': deletion.serialize(req)})


class DeletionRequestApproveView(_Decision):
    allowed_roles = APPROVER_ROLES

    def post(self, request, store_id, request_id):
        return self.finish(store_id, deletion.approve, user=request.user, request_id=request_id, note=_note(request))


class DeletionRequestRejectView(_Decision):
    allowed_roles = APPROVER_ROLES

    def post(self, request, store_id, request_id):
        return self.finish(store_id, deletion.reject, user=request.user, request_id=request_id, note=_note(request))


class DeletionRequestCancelView(_Decision):
    allowed_roles = None

    def post(self, request, store_id, request_id):
        return self.finish(store_id, deletion.cancel, user=request.user, request_id=request_id)
