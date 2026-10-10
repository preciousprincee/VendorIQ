"""
Generates the per-user "your plan is about to run out" notifications.

There is no background scheduler in this project, so these are created lazily
- the first time a user's bell is polled inside a reminder window. Each
reminder has a dedupe_key, so polling every two minutes still creates exactly
one notification per (period, threshold).
"""
import logging
import math
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.entitlements import get_subscription
from apps.billing.models import SubscriptionStatus, get_trial_period_days
from .models import Notification

logger = logging.getLogger(__name__)

TRIAL_THRESHOLDS = (5, 2, 1)          # "trial ends in N days"
SUBSCRIPTION_THRESHOLDS = (7, 3, 1)   # "plan expires in N days"
EXPIRED_NOTICE_WINDOW_DAYS = 14       # how long "your plan has expired" keeps being created for


def _threshold(days_left, thresholds):
    """Smallest threshold that days_left has reached (e.g. 2 days left with (7,3,1) -> 3), or None."""
    for t in sorted(thresholds):
        if days_left <= t:
            return t
    return None


def _create_once(user, dedupe_key, **fields):
    try:
        with transaction.atomic():
            Notification.objects.get_or_create(user=user, dedupe_key=dedupe_key, defaults=fields)
    except IntegrityError:
        pass  # a concurrent poll created it first - exactly what we wanted


def _plural(n, word):
    return f'{n} {word}' + ('' if n == 1 else 's')


def ensure_subscription_notifications(user):
    sub = get_subscription(user)
    if sub.is_complimentary:
        return
    now = timezone.now()

    if sub.status == SubscriptionStatus.TRIAL and sub.is_trial_active:
        days = sub.trial_days_remaining
        t = _threshold(days, TRIAL_THRESHOLDS) if days >= 1 else None
        if t is not None:
            _create_once(
                user, f'trial-ending:{sub.trial_started_at:%Y%m%d}:{t}',
                kind=Notification.Kind.TRIAL_ENDING, severity='medium' if days > 1 else 'high',
                title='Your free trial is ending soon',
                message=f'Your Pro trial ends in {_plural(days, "day")}. Upgrade to keep Pro features like the AI assistant and unlimited products.',
                link='/subscription',
            )
        return

    if sub.is_pro_active and sub.current_period_end:
        days = math.ceil((sub.current_period_end - now).total_seconds() / 86400)
        t = _threshold(days, SUBSCRIPTION_THRESHOLDS) if days >= 1 else None
        if t is not None:
            end_text = f'{sub.current_period_end:%b} {sub.current_period_end.day}, {sub.current_period_end:%Y}'
            if sub.cancel_at_period_end:
                message = f'Your Pro plan will end on {end_text} ({_plural(days, "day")} left) because it was cancelled. Resume it any time to keep Pro.'
            else:
                message = f'Your Pro plan expires in {_plural(days, "day")} (on {end_text}). Renew to keep your Pro features.'
            _create_once(
                user, f'subscription-expiring:{sub.current_period_end:%Y%m%d}:{t}',
                kind=Notification.Kind.SUBSCRIPTION_EXPIRING, severity='medium' if days > 1 else 'high',
                title='Your Pro plan is expiring soon', message=message, link='/subscription',
            )
        return

    if sub.status == SubscriptionStatus.EXPIRED:
        ended = sub.current_period_end
        if ended is None and sub.trial_started_at:
            ended = sub.trial_started_at + timedelta(days=get_trial_period_days())
        if ended and now - ended <= timedelta(days=EXPIRED_NOTICE_WINDOW_DAYS):
            _create_once(
                user, f'subscription-expired:{ended:%Y%m%d}',
                kind=Notification.Kind.SUBSCRIPTION_EXPIRED, severity='high',
                title='Your Pro access has ended',
                message='Your account is now on the Free plan. Upgrade any time to get your Pro features back.',
                link='/subscription',
            )
