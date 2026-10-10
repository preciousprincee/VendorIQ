from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0002_aisettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatmessage',
            name='deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
