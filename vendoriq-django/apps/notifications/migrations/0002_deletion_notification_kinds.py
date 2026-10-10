from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='kind',
            field=models.CharField(choices=[('trial_ending', 'Trial ending'), ('subscription_expiring', 'Subscription expiring'), ('subscription_expired', 'Subscription expired'), ('deletion_request', 'Product deletion request'), ('deletion_decision', 'Product deletion decision'), ('general', 'General')], default='general', max_length=30),
        ),
    ]
