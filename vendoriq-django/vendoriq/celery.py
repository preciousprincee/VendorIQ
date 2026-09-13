import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vendoriq.settings')

app = Celery('vendoriq')
# Namespaced settings: every Celery-related setting in settings.py is
# prefixed CELERY_ (e.g. CELERY_BROKER_URL), so it's easy to see at a glance
# which Django settings actually configure Celery.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
