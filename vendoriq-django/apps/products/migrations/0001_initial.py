import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('stores', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('barcode', models.CharField(blank=True, max_length=100, null=True)),
                ('cost_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('selling_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('quantity', models.IntegerField(default=0)),
                ('low_stock_threshold', models.IntegerField(default=5)),
                ('category', models.CharField(blank=True, max_length=100, null=True)),
                ('supplier', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='products', to='stores.store')),
            ],
            options={
                'db_table': 'products',
            },
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['store', 'barcode'], name='products_store_i_9c0d3f_idx'),
        ),
    ]
