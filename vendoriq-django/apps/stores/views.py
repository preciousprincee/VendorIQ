from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.db.models.deletion import ProtectedError
from .models import Store, Staff
from .serializers import StoreSerializer, StaffSerializer
from .permissions import require_store_access
from .base_views import StoreScopedAPIView
from apps.authentication.models import User
from apps.billing.entitlements import check_can_add_store, check_can_add_staff


class StoreListCreateView(APIView):
    """
    No store_id in this URL at all (listing/creating stores themselves,
    not something scoped to one) - StoreScopedAPIView has nothing to
    resolve here, so this stays a plain APIView.
    """

    def get(self, request):
        owned = Store.objects.filter(owner=request.user)
        staff_roles = Staff.objects.filter(user=request.user).select_related('store')
        owned_data = StoreSerializer(owned, many=True).data
        for s in owned_data:
            s['role'] = 'OWNER'
        staff_data = []
        for sr in staff_roles:
            store_data = StoreSerializer(sr.store).data
            store_data['role'] = sr.role
            staff_data.append(store_data)
        return Response({'owned': owned_data, 'staff': staff_data})

    def post(self, request):
        serializer = StoreSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'error': next(iter(serializer.errors.values()))[0]}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            # Lock the user's own row for the check+create so two
            # concurrent "create store" requests can't both pass
            # check_can_add_store's count check before either has actually
            # created their store - without this, a Free-plan user (limit:
            # 1 store) could end up owning 2 if a double-tap or two open
            # tabs both fire at once.
            User.objects.select_for_update().get(id=request.user.id)
            check_can_add_store(request.user)
            store = serializer.save(owner=request.user)
        return Response({'store': StoreSerializer(store).data}, status=status.HTTP_201_CREATED)


class StoreDetailView(StoreScopedAPIView):
    allowed_roles = None  # any staff member can view; edit/delete narrow further below

    def get(self, request, store_id):
        return Response({'store': StoreSerializer(self.store).data})

    def patch(self, request, store_id):
        require_store_access(self.store, request.user, ['OWNER'])
        serializer = StoreSerializer(self.store, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'store': serializer.data})
        return Response({'error': next(iter(serializer.errors.values()))[0]}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, store_id):
        require_store_access(self.store, request.user, ['OWNER'])
        try:
            self.store.delete()
        except ProtectedError:
            # Store -> Product cascades fine, but Product is PROTECTed by
            # both SaleItem and InvoiceItem (financial records shouldn't
            # silently vanish or dangle) - so deleting a store cascades
            # into trying to delete its products, which fails the moment
            # any of them have ever been sold or invoiced. That's the
            # NORMAL case for any real, used store, not an edge case -
            # without this catch, "Delete store" is effectively broken for
            # almost every store that has actual history, with nothing but
            # a raw 500 to show for it.
            return Response(
                {'error': "This store has sales or invoice history and can't be deleted, since that would destroy those financial records. Contact support if you need to permanently close this store."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({'message': 'Store deleted successfully.'})


class StaffListCreateView(StoreScopedAPIView):
    allowed_roles = ['OWNER', 'MANAGER']

    def get(self, request, store_id):
        staff = Staff.objects.filter(store=self.store).select_related('user')
        return Response({'staff': StaffSerializer(staff, many=True).data})

    def post(self, request, store_id):
        store = self.store
        email = request.data.get('email')
        role = request.data.get('role', 'CASHIER')
        # 'OWNER' is a real value in StaffRole.choices (Staff.role is a
        # plain CharField - Django does NOT enforce `choices` at the
        # ORM/.save() level, only in forms/admin), and this endpoint is
        # reachable by a MANAGER, not just the store owner (allowed_roles
        # above). Without this check, a manager could POST
        # {"role": "OWNER"} for any registered email (including a second
        # account of their own) and silently grant that account full
        # owner-level access - get_store_role() returns whatever string is
        # in this column, and every allowed_roles=['OWNER'] check in the
        # backend (store deletion, profitability, exports, subscription
        # billing, ...) would then pass for them. OWNER is never a valid
        # Staff role - store ownership is Store.owner, a separate field
        # entirely, not represented as a Staff row at all.
        if role not in ['MANAGER', 'CASHIER']:
            return Response({'error': 'Invalid role.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'No user found with that email. They must register first.'}, status=status.HTTP_404_NOT_FOUND)
        if user.id == store.owner_id:
            return Response({'error': "You're already the owner of this store - you can't add yourself as staff."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Lock the store row so two concurrent "add staff" requests
            # can't both pass check_can_add_staff's count check (or the
            # duplicate-staff check just below) before either has actually
            # created their Staff row - without this, a Free-plan store
            # (limit: 1 user, i.e. no staff at all) could briefly end up
            # with 2 staff added at once, and inviting the same email
            # twice in quick succession could hit an unhandled IntegrityError
            # from the store+user unique_together constraint instead of
            # this clean 409.
            Store.objects.select_for_update().get(id=store.id)
            check_can_add_staff(store)
            if Staff.objects.filter(store=store, user=user).exists():
                return Response({'error': 'User is already a staff member.'}, status=status.HTTP_409_CONFLICT)
            staff = Staff.objects.create(store=store, user=user, role=role)
        return Response({'staff': StaffSerializer(staff).data}, status=status.HTTP_201_CREATED)


class StaffDetailView(StoreScopedAPIView):
    allowed_roles = ['OWNER']

    def patch(self, request, store_id, staff_id):
        try:
            staff = Staff.objects.get(id=staff_id, store=self.store)
        except Staff.DoesNotExist:
            return Response({'error': 'Staff member not found.'}, status=status.HTTP_404_NOT_FOUND)
        role = request.data.get('role')
        if role not in ['MANAGER', 'CASHIER']:
            return Response({'error': 'Invalid role.'}, status=status.HTTP_400_BAD_REQUEST)
        staff.role = role
        staff.save()
        return Response({'staff': StaffSerializer(staff).data})

    def delete(self, request, store_id, staff_id):
        try:
            staff = Staff.objects.get(id=staff_id, store=self.store)
        except Staff.DoesNotExist:
            return Response({'error': 'Staff member not found.'}, status=status.HTTP_404_NOT_FOUND)
        staff.delete()
        return Response({'message': 'Staff member removed.'})
