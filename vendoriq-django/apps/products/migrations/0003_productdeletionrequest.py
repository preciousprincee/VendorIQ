import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0002_product_photo'),
        ('stores', '0002_fix_staff_owner_role'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductDeletionRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('product_name', models.CharField(max_length=255)),
                ('remark', models.CharField(max_length=300)),
                ('status', models.CharField(choices=[('PENDING', 'Waiting for approval'), ('APPROVED', 'Approved (product deleted)'), ('REJECTED', 'Rejected'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=10)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decision_note', models.CharField(blank=True, default='', max_length=300)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deletion_requests', to='products.product')),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_deletion_requests', to='stores.store')),
            ],
            options={'db_table': 'product_deletion_requests', 'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='productdeletionrequest',
            constraint=models.UniqueConstraint(condition=Q(('status', 'PENDING')), fields=('product',), name='product_one_pending_deletion_request'),
        ),
    ]
