import logging
import uuid
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.insights.views import FINANCIAL_ROLES, compute_store_alerts
from apps.stores.models import Store
from apps.stores.permissions import get_store_role
from .models import Announcement, Notification, NotificationSeen
from .services import ensure_subscription_notifications

logger = logging.getLogger(__name__)

ANNOUNCEMENT_WINDOW = timedelta(days=30)
PERSONAL_WINDOW = timedelta(days=60)


class NotificationListView(APIView):
    """
    GET /api/notifications/?store=<uuid>

    Everything that belongs in the bell, newest first: the user's own
    notifications (subscription reminders), admin announcements to all users,
    and - for owners/managers of the given store - its stock/invoice alerts.
    Each item carries `unread`; `unreadCount` is what the badge shows.
    """

    def get(self, request):
        user = request.user
        now = timezone.now()

        try:
            ensure_subscription_notifications(user)
        except Exception:
            # The bell must never break the app because a reminder failed to generate.
            logger.error('Could not generate subscription notifications for %s', user.pk, exc_info=True)

        items = []
        for n in Notification.objects.filter(user=user, created_at__gte=now - PERSONAL_WINDOW)[:30]:
            items.append({
                'id': f'n-{n.id}', 'type': n.kind, 'severity': n.severity, 'title': n.title,
                'message': n.message, 'link': n.link, 'createdAt': n.created_at,
            })

        # "To all users" means everyone who existed when it was sent. Without
        # the created_at floor a brand-new account opened its bell to a stack
        # of weeks-old announcements, all counted as unread.
        announcements = Announcement.objects.filter(
            is_active=True, created_at__gte=max(now - ANNOUNCEMENT_WINDOW, user.created_at),
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )[:20]
        for a in announcements:
            items.append({
                'id': f'a-{a.id}', 'type': 'announcement', 'severity': 'low', 'title': a.title,
                'message': a.message, 'link': a.link, 'createdAt': a.created_at,
            })

        store_id = request.query_params.get('store')
        if store_id:
            try:
                store = Store.objects.filter(pk=uuid.UUID(store_id)).first()
            except ValueError:
                store = None
            if store is not None and get_store_role(store, user) in FINANCIAL_ROLES:
                items.extend(dict(alert) for alert in compute_store_alerts(store)['notifications'])

        items.sort(key=lambda n: n['createdAt'], reverse=True)

        seen = NotificationSeen.objects.filter(user=user).first()
        seen_at = seen.seen_at if seen else None
        for item in items:
            item['unread'] = seen_at is None or item['createdAt'] > seen_at

        return Response({
            'notifications': items,
            'unreadCount': sum(1 for i in items if i['unread']),
            'seenAt': seen_at,
        })


class NotificationSeenView(APIView):
    """POST /api/notifications/seen/ - the person opened the bell; everything up to now is read."""

    def post(self, request):
        now = timezone.now()
        NotificationSeen.objects.update_or_create(user=request.user, defaults={'seen_at': now})
        return Response({'seenAt': now, 'unreadCount': 0})
