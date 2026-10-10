"""
Server-side product analytics (PostHog).

Used for the events that matter most and must not depend on the browser: sign-up, email/phone
verification, trial start and - above all - purchases, which are confirmed by Paystack's webhook even if
the customer has closed the tab. The browser sends the UI events (page views, till actions...) with the
same opaque user id, so PostHog shows one person.

Guarantees:
  * Does nothing unless POSTHOG_API_KEY is set (local dev, tests, forks send nothing).
  * Can NEVER break a request: every failure is logged and swallowed. posthog-python also sends from a
    background thread, so a slow or unreachable PostHog never delays a response.
  * Sent only after the surrounding database transaction commits (transaction.on_commit): an event is
    never recorded for something that was rolled back.
  * People are identified by user id only. Personal-looking property names are stripped as a safety net.
"""
import logging
import os
import re
import threading

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# Never leave the server, even if a call site passes them by mistake.
_BLOCKED = re.compile(r'^(e-?mail|phone|mobile|name|first_?name|last_?name|full_?name|address|password|token|customer(_?name)?|note|remark|barcode|receipt_?no|reference|ip(_?address)?)$', re.I)

_lock = threading.Lock()
_client = None
_client_pid = None


def _get_client():
    """One client per process (a gunicorn worker forks AFTER import, so it is created lazily and re-created if the pid changes)."""
    global _client, _client_pid
    key = getattr(settings, 'POSTHOG_API_KEY', '')
    if not key:
        return None
    with _lock:
        if _client is None or _client_pid != os.getpid():
            from posthog import Posthog   # imported lazily: an uninstalled package must not break startup when analytics is off
            _client = Posthog(project_api_key=key, host=getattr(settings, 'POSTHOG_HOST', 'https://us.i.posthog.com'))
            _client_pid = os.getpid()
        return _client


def _clean(props):
    return {k: v for k, v in (props or {}).items() if not _BLOCKED.match(str(k)) and v is not None}


def _send(distinct_id, event, properties):
    try:
        client = _get_client()
        if client is not None:
            # Keyword arguments: valid for every posthog-python release (the positional order changed in v6).
            client.capture(distinct_id=distinct_id, event=event, properties=properties)
    except Exception:
        logger.warning('PostHog capture failed for event=%s (ignored)', event, exc_info=True)


def capture(who, event, properties=None, *, set_props=None):
    """
    capture(user, 'trial_started', {'source': 'api'}, set_props={'plan': 'PRO'})

    `who` is a User (or a user id). `set_props` updates the person's own properties (plan, role...).
    """
    try:
        if not getattr(settings, 'POSTHOG_API_KEY', ''):
            return
        distinct_id = str(getattr(who, 'pk', who) or '')
        if not distinct_id:
            return
        props = _clean(properties)
        props['source'] = 'server'
        if set_props:
            props['$set'] = _clean(set_props)
        transaction.on_commit(lambda: _send(distinct_id, event, props))
    except Exception:
        logger.warning('PostHog capture could not be scheduled for event=%s (ignored)', event, exc_info=True)
