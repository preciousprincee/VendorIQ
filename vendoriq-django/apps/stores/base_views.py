from rest_framework.views import APIView

from .permissions import get_store_or_404, require_store_access


class StoreScopedAPIView(APIView):
    """
    Base class for any endpoint scoped to a single store, i.e. anything
    mounted under /api/stores/<uuid:store_id>/...

    Why this exists: every one of these views used to open with the same
    two lines -
        store = get_store_or_404(store_id, request.user)
        require_store_access(store, request.user, [...])
    - repeated by hand in every method of every view. That's a convention,
    not a guarantee: it's entirely possible to add a new view, forget those
    two lines, and ship an endpoint with no tenant-isolation check at all -
    nothing in the type system or request pipeline would catch it.

    Subclassing this instead makes store resolution + the baseline access
    check happen in DRF's `initial()` hook, before your handler method ever
    runs - you cannot reach `get`/`post`/`delete`/etc. without it having
    happened, the same way you can't skip authentication. `self.store` and
    `self.role` are already resolved and available by the time your method
    body executes.

    This does not replace per-action role checks - a view that most staff
    can view but only OWNER/MANAGER can delete still calls
    `require_store_access(self.store, request.user, ['OWNER', 'MANAGER'])`
    explicitly inside `delete()`. What this guarantees is the floor: you can
    never accidentally ship a store-scoped endpoint with zero tenant check.

    Usage:
        class ProductListCreateView(StoreScopedAPIView):
            allowed_roles = None  # any staff member with store access

            def get(self, request, store_id):
                products = Product.objects.filter(store=self.store)
                ...

        class SaleDetailView(StoreScopedAPIView):
            def delete(self, request, store_id, sale_id):
                # self.role already resolved; add a stricter/method-specific
                # check here when the class-level default isn't enough.
                if self.role == 'CASHIER' and sale.recorded_by_id != request.user.id:
                    ...

    Migration status: every store-scoped view across sales, products,
    expenses, invoices, insights, staff/store management, and the AI
    assistant's chat history now uses this base class. Two views remain on
    the older explicit get_store_or_404/require_store_access pattern by
    necessity, not oversight:
    - StoreListCreateView (stores app): lists/creates stores themselves -
      there's no single store_id to scope to.
    - ChatView (ai app): store_id arrives in the POST body (`storeId`), not
      the URL, since the store is chosen client-side - this class resolves
      store_id from URL kwargs, so it has nothing to hook into there.
    """
    allowed_roles = None  # override on subclasses to restrict at the class level

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        store_id = kwargs.get('store_id')
        if store_id is not None:
            self.store = get_store_or_404(store_id, request.user)
            self.role = require_store_access(self.store, request.user, self.allowed_roles)
