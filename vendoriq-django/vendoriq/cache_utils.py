"""
Small shared caching helpers used by the insights/expenses/products/sales
views to keep the most expensive, most frequently-hit read endpoints
(dashboard aggregation, trend charts, profitability, notifications) cheap
under concurrent load from many stores/users at once.

Design:
- Every cache key is scoped to a single store, so one store's traffic can
  never evict or return another store's numbers.
- Reads go through safe_cache_get/safe_cache_set, which never raise - a
  cache backend hiccup degrades to "just recompute from the database"
  instead of turning into a 500 for the user. (With django-redis this is
  belt-and-braces on top of IGNORE_EXCEPTIONS in settings.py; with the
  locmem fallback it can't fail anyway.)
- Every write path (sale recorded/deleted, expense added/edited/deleted,
  product added/edited/deleted/restocked) calls invalidate_store_insights()
  so nobody ever sees stale figures after making a change.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Short TTLs - these are safety nets against a burst of concurrent requests
# recomputing the same aggregation, not a long-lived source of truth. Every
# write path explicitly invalidates anyway, so staleness is bounded by
# whichever is shorter: the TTL below, or the next write to that store.
DASHBOARD_TTL = 60
TREND_TTL = 300
NOTIFICATIONS_TTL = 45
PROFITABILITY_TTL = 60

# TrendView is parameterised by ?days=, so we can't wildcard-delete a single
# key on invalidation (locmem has no key-pattern scan). Instead we eagerly
# bust the handful of day-ranges the UI actually offers (7/30/90 on Insights,
# 14 on the dashboard sparkline) plus a couple of extra common ones.
KNOWN_TREND_WINDOWS = (7, 14, 30, 60, 90)


def _key(prefix, store_id, *parts):
    key = f'viq:{prefix}:{store_id}'
    if parts:
        key += ':' + ':'.join(str(p) for p in parts)
    return key


def dashboard_key(store_id):
    return _key('dashboard', store_id)


def trend_key(store_id, days):
    return _key('trend', store_id, days)


def notifications_key(store_id):
    return _key('notifications', store_id)


def profitability_key(store_id):
    return _key('profitability', store_id)


def safe_cache_get(key):
    try:
        return cache.get(key)
    except Exception:
        logger.warning('Cache read failed for key %s - falling back to DB', key, exc_info=True)
        return None


def safe_cache_set(key, value, ttl):
    try:
        cache.set(key, value, ttl)
    except Exception:
        logger.warning('Cache write failed for key %s - continuing without caching it', key, exc_info=True)


def invalidate_store_insights(store_id):
    """
    Call this from every view that changes sales, expenses, or products for
    a store. Clears everything derived from that data so the next read is
    always fresh instead of serving stale figures until a TTL expires.
    """
    keys = [
        dashboard_key(store_id),
        notifications_key(store_id),
        profitability_key(store_id),
    ]
    keys += [trend_key(store_id, d) for d in KNOWN_TREND_WINDOWS]
    try:
        cache.delete_many(keys)
    except Exception:
        logger.warning('Cache invalidation failed for store %s - entries will expire via TTL instead', store_id, exc_info=True)
