# Makes shared_task-decorated functions use this Celery app automatically,
# and ensures the app is loaded whenever Django starts.
from .celery import app as celery_app

__all__ = ('celery_app',)
