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
            name='Expense',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('category', models.CharField(choices=[('RENT', 'Rent'), ('UTILITIES', 'Utilities'), ('SALARIES', 'Salaries'), ('TRANSPORT', 'Transport'), ('PACKAGING', 'Packaging'), ('MAINTENANCE', 'Maintenance'), ('MISCELLANEOUS', 'Miscellaneous'), ('OTHER', 'Other')], default='MISCELLANEOUS', max_length=20)),
                ('description', models.CharField(max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('frequency', models.CharField(choices=[('ONE_OFF', 'One-off'), ('DAILY', 'Daily'), ('WEEKLY', 'Weekly'), ('MONTHLY', 'Monthly'), ('YEARLY', 'Yearly')], default='ONE_OFF', max_length=10)),
                ('is_overhead', models.BooleanField(default=False, help_text='Recurring running cost (rent, salaries, utilities) vs a one-off miscellaneous expense.')),
                ('incurred_on', models.DateField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='expenses', to='stores.store')),
            ],
            options={
                'db_table': 'expenses',
                'ordering': ['-incurred_on', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='expense',
            index=models.Index(fields=['store', 'incurred_on'], name='expenses_store_i_j1k2l3_idx'),
        ),
    ]
