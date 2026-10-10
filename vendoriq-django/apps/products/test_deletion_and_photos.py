"""
Cashier deletion requests (remark -> owner + managers notified -> approve/reject)
and the product-photo rules (size cap, one small photo, tidy storage).
"""
import io
import os
import random

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.notifications.models import Notification
from apps.products.models import Product, ProductDeletionRequest


def _product(store, **kw):
    d = dict(name='Mistake Item', cost_price='100.00', selling_price='150.00', quantity=10)
    d.update(kw)
    return Product.objects.create(store=store, **d)


def _ask(client, store, product, remark='Added this by mistake'):
    return client.post(f'/api/stores/{store.id}/products/{product.id}/deletion-request/', {'remark': remark}, format='json')


def _decide(client, store, request_id, action, **body):
    return client.post(f'/api/stores/{store.id}/deletion-requests/{request_id}/{action}/', body, format='json')


def _kinds(user):
    return sorted(Notification.objects.filter(user=user).values_list('kind', flat=True))


@pytest.mark.django_db
class TestRequestingDeletion:
    def test_request_is_recorded_and_owner_and_manager_are_notified(self, cashier_client, store, owner_user, manager_user, cashier_user, manager_staff):
        p = _product(store)
        r = _ask(cashier_client, store, p, 'Duplicate of the rice entry')
        assert r.status_code == 201 and r.data['request']['status'] == 'PENDING'
        assert ProductDeletionRequest.objects.get().remark == 'Duplicate of the rice entry'
        assert _kinds(owner_user) == ['deletion_request'] and _kinds(manager_user) == ['deletion_request']
        assert _kinds(cashier_user) == []            # the requester is not asked to approve their own request
        note = Notification.objects.get(user=owner_user)
        assert 'Duplicate of the rice entry' in note.message and note.link == '/products?requests=1'
        p.refresh_from_db()                           # nothing is deleted yet

    def test_a_remark_is_required_and_bounded(self, cashier_client, store):
        p = _product(store)
        assert _ask(cashier_client, store, p, '').status_code == 400
        assert _ask(cashier_client, store, p, '  ok ').status_code == 400          # too short once trimmed
        assert _ask(cashier_client, store, p, 'x' * 301).status_code == 400
        assert ProductDeletionRequest.objects.count() == 0

    def test_owners_and_managers_delete_directly_so_they_are_told_not_to_request(self, owner_client, manager_client, store):
        p = _product(store)
        assert _ask(owner_client, store, p).status_code == 400
        assert _ask(manager_client, store, p).status_code == 400

    def test_a_second_request_for_the_same_product_is_refused(self, cashier_client, store, owner_user):
        p = _product(store)
        assert _ask(cashier_client, store, p).status_code == 201
        assert _ask(cashier_client, store, p).status_code == 409
        assert Notification.objects.filter(user=owner_user).count() == 1

    def test_a_product_with_sales_history_is_refused_immediately(self, owner_client, cashier_client, store):
        p = _product(store)
        owner_client.post(f'/api/stores/{store.id}/sales/', {'items': [{'productId': str(p.id), 'quantity': 1}]}, format='json')
        r = _ask(cashier_client, store, p)
        assert r.status_code == 409 and 'history' in r.data['error']
        assert ProductDeletionRequest.objects.count() == 0

    def test_a_cashier_cannot_ask_about_another_stores_product(self, cashier_client, other_owner_user):
        from apps.stores.models import Store
        other = Store.objects.create(owner=other_owner_user, name='Other')
        p = _product(other)
        assert _ask(cashier_client, other, p).status_code in (403, 404)


@pytest.mark.django_db
class TestDecisions:
    def test_approval_deletes_the_product_and_closes_the_loop(self, cashier_client, manager_client, store, owner_user, manager_user, cashier_user, manager_staff):
        p = _product(store)
        req = _ask(cashier_client, store, p).data['request']
        r = _decide(manager_client, store, req['id'], 'approve', note='Good catch')
        assert r.status_code == 200 and r.data['request']['status'] == 'APPROVED'
        assert not Product.objects.filter(pk=p.pk).exists()
        saved = ProductDeletionRequest.objects.get(pk=req['id'])
        assert saved.decided_by == manager_user and saved.product_name == 'Mistake Item'   # the record outlives the product
        assert _kinds(cashier_user) == ['deletion_decision']                                # requester is told
        assert 'Good catch' in Notification.objects.get(user=cashier_user).message
        assert _kinds(owner_user) == [] and _kinds(manager_user) == []                      # answered: gone from every approver's bell

    def test_rejection_keeps_the_product_and_tells_the_cashier_why(self, cashier_client, owner_client, store, cashier_user):
        p = _product(store)
        req = _ask(cashier_client, store, p).data['request']
        r = _decide(owner_client, store, req['id'], 'reject', note='We still sell it')
        assert r.status_code == 200 and r.data['request']['status'] == 'REJECTED'
        assert Product.objects.filter(pk=p.pk).exists()
        assert 'We still sell it' in Notification.objects.get(user=cashier_user).message

    def test_cashiers_cannot_decide(self, cashier_client, store):
        req = _ask(cashier_client, store, _product(store)).data['request']
        assert _decide(cashier_client, store, req['id'], 'approve').status_code == 403
        assert _decide(cashier_client, store, req['id'], 'reject').status_code == 403
        assert Product.objects.count() == 1

    def test_approving_works_end_to_end_with_no_server_error(self, cashier_client, owner_client, store):
        # Regression: approve() used to delete the product through the relation cached on the
        # request, then save the request -> "save() prohibited ... unsaved related object" (HTTP 500).
        p = _product(store, name='Cashier Mistake')
        req = _ask(cashier_client, store, p).data['request']
        r = _decide(owner_client, store, req['id'], 'approve')
        assert r.status_code == 200, r.data
        assert not Product.objects.filter(pk=p.pk).exists()
        saved = ProductDeletionRequest.objects.get(pk=req['id'])
        assert saved.status == 'APPROVED' and saved.product_id is None and saved.product_name == 'Cashier Mistake'

    def test_deleting_a_product_directly_settles_its_pending_request(self, cashier_client, owner_client, store, cashier_user):
        p = _product(store)
        req = _ask(cashier_client, store, p).data['request']
        assert owner_client.delete(f'/api/stores/{store.id}/products/{p.id}/').status_code == 200
        saved = ProductDeletionRequest.objects.get(pk=req['id'])
        assert saved.status == 'APPROVED' and 'Deleted directly' in saved.decision_note
        assert owner_client.get(f'/api/stores/{store.id}/deletion-requests/').data['requests'] == []   # no ghost left in the review list
        assert _kinds(cashier_user) == ['deletion_decision']

    def test_direct_delete_of_a_product_with_history_still_refuses_and_keeps_the_request(self, owner_client, cashier_client, store):
        p = _product(store)
        req = _ask(cashier_client, store, p).data['request']
        owner_client.post(f'/api/stores/{store.id}/sales/', {'items': [{'productId': str(p.id), 'quantity': 1}]}, format='json')
        assert owner_client.delete(f'/api/stores/{store.id}/products/{p.id}/').status_code == 409
        assert Product.objects.filter(pk=p.pk).exists()
        assert ProductDeletionRequest.objects.get(pk=req['id']).status == 'PENDING'

    def test_a_request_can_only_be_decided_once(self, cashier_client, owner_client, store):
        req = _ask(cashier_client, store, _product(store)).data['request']
        assert _decide(owner_client, store, req['id'], 'reject').status_code == 200
        assert _decide(owner_client, store, req['id'], 'approve').status_code == 409

    def test_a_sale_made_after_the_request_blocks_approval_and_keeps_it_pending(self, cashier_client, owner_client, store):
        p = _product(store)
        req = _ask(cashier_client, store, p).data['request']
        owner_client.post(f'/api/stores/{store.id}/sales/', {'items': [{'productId': str(p.id), 'quantity': 1}]}, format='json')
        r = _decide(owner_client, store, req['id'], 'approve')
        assert r.status_code == 409 and 'history' in r.data['error']
        assert Product.objects.filter(pk=p.pk).exists()
        assert ProductDeletionRequest.objects.get(pk=req['id']).status == 'PENDING'     # approver can still reject it
        assert _decide(owner_client, store, req['id'], 'reject', note='It sold today').status_code == 200

    def test_only_the_requester_can_cancel(self, cashier_client, owner_client, store):
        req = _ask(cashier_client, store, _product(store)).data['request']
        url = f"/api/stores/{store.id}/deletion-requests/{req['id']}/cancel/"
        assert owner_client.post(url).status_code == 403
        assert cashier_client.post(url).status_code == 200
        assert ProductDeletionRequest.objects.get().status == 'CANCELLED'

    def test_who_sees_which_requests(self, cashier_client, owner_client, store):
        _ask(cashier_client, store, _product(store, name='A'))
        url = f'/api/stores/{store.id}/deletion-requests/'
        assert len(owner_client.get(url).data['requests']) == 1 and len(cashier_client.get(url).data['requests']) == 1
        req = ProductDeletionRequest.objects.get()
        _decide(owner_client, store, req.id, 'reject')
        assert owner_client.get(url).data['requests'] == []                         # default: pending only
        assert len(owner_client.get(url + '?status=ALL').data['requests']) == 1

    def test_direct_deletion_rules_are_unchanged(self, owner_client, cashier_client, store):
        p = _product(store)
        assert cashier_client.delete(f'/api/stores/{store.id}/products/{p.id}/').status_code == 403
        assert owner_client.delete(f'/api/stores/{store.id}/products/{p.id}/').status_code == 200


def _image_bytes(w, h, fmt='JPEG', quality=70):
    random.seed(3)
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255 // w + random.randint(0, 40)) % 256, (y * 255 // h + random.randint(0, 40)) % 256, 128)
    buf = io.BytesIO()
    img.save(buf, fmt, **({'quality': quality} if fmt == 'JPEG' else {}))
    return buf.getvalue()


def _create(client, store, photo=None, **extra):
    body = {'name': 'Photo Item', 'cost_price': '10', 'selling_price': '20', 'quantity': '5', **extra}
    if photo is not None:
        body['photo'] = photo
    return client.post(f'/api/stores/{store.id}/products/', body, format='multipart')


@pytest.mark.django_db
class TestProductPhotos:
    @pytest.fixture(autouse=True)
    def media(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        return tmp_path

    def test_an_oversized_upload_is_refused(self, owner_client, store):
        big = SimpleUploadedFile('big.png', _image_bytes(1600, 1200, 'PNG'), 'image/png')
        r = _create(owner_client, store, big)
        assert r.status_code == 400 and 'too large' in r.data['error']
        assert Product.objects.count() == 0

    def test_a_normal_photo_is_stored_as_one_small_file(self, owner_client, store, media):
        r = _create(owner_client, store, SimpleUploadedFile('p.jpg', _image_bytes(1200, 900), 'image/jpeg'))
        assert r.status_code == 201
        product = Product.objects.get()
        assert product.photo.name.endswith('.webp') and product.photo.size <= 250 * 1024
        assert len(os.listdir(media / 'products')) == 1

    def test_something_that_is_not_an_image_is_refused(self, owner_client, store):
        r = _create(owner_client, store, SimpleUploadedFile('evil.jpg', b'not really a picture', 'image/jpeg'))
        assert r.status_code == 400

    def test_replacing_the_photo_deletes_the_old_file(self, owner_client, store, media, django_capture_on_commit_callbacks):
        _create(owner_client, store, SimpleUploadedFile('a.jpg', _image_bytes(800, 600), 'image/jpeg'))
        product = Product.objects.get()
        first = product.photo.name
        with django_capture_on_commit_callbacks(execute=True):   # file cleanup runs on commit
            r = owner_client.patch(f'/api/stores/{store.id}/products/{product.id}/',
                                   {'photo': SimpleUploadedFile('b.jpg', _image_bytes(700, 500), 'image/jpeg')}, format='multipart')
        assert r.status_code == 200
        product.refresh_from_db()
        assert product.photo.name != first
        files = os.listdir(media / 'products')
        assert len(files) == 1 and os.path.basename(first) not in files        # only ever ONE photo per product

    def test_deleting_the_product_deletes_its_photo(self, owner_client, store, media, django_capture_on_commit_callbacks):
        _create(owner_client, store, SimpleUploadedFile('a.jpg', _image_bytes(800, 600), 'image/jpeg'))
        product = Product.objects.get()
        with django_capture_on_commit_callbacks(execute=True):
            assert owner_client.delete(f'/api/stores/{store.id}/products/{product.id}/').status_code == 200
        assert os.listdir(media / 'products') == []

    def test_selling_a_product_does_not_touch_its_photo(self, owner_client, store, media):
        _create(owner_client, store, SimpleUploadedFile('a.jpg', _image_bytes(800, 600), 'image/jpeg'))
        product = Product.objects.get()
        owner_client.post(f'/api/stores/{store.id}/sales/', {'items': [{'productId': str(product.id), 'quantity': 1}]}, format='json')
        assert len(os.listdir(media / 'products')) == 1
