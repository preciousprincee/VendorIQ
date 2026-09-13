"""
Extra admin-only pages that aren't tied to a single Django model, so they
can't be a ModelAdmin - each is a plain view rendering a template that
extends admin/base.html (same pattern vendoriq/admin_dashboard.py's index
page uses) to keep Unfold's sidebar/header chrome. Wired into
vendoriq/urls.py under the admin/ prefix, wrapped with admin.site.admin_view
(the same mechanism Django's own admin.site.urls uses internally) rather
than a bare @staff_member_required - that gets us the same permission
check, CSRF handling, and "next" redirect-to-login behavior as every other
admin page for free, instead of half-reimplementing it.

None of this touches /api/... - it's purely additive pages under /admin/,
so it can't affect the React app or anything the mobile/desktop product
depends on.
"""
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.shortcuts import render
from django.utils import timezone

from apps.billing.models import Subscription, get_trial_period_days, get_pro_price_ngn
from apps.billing.plans import PLANS
from .admin_dashboard import compute_subscription_metrics, _daily_series, _svg_points


def _admin_context(request, title):
    """
    Same context Django's own AdminSite.index() would give a template
    extending admin/base.html (site_header, has_permission, breadcrumbs,
    etc.) - without it, these standalone views would render inside the
    admin chrome but with things like the site title/branding missing or
    wrong. admin.site.each_context() is the exact method Django's built-in
    admin views call for this.
    """
    context = admin.site.each_context(request)
    context.update({'title': title})
    return context


def revenue_view(request):
    """
    Deeper dive than the dashboard's summary cards: the same MRR/ARR/plan
    breakdown (via compute_subscription_metrics, shared with the main
    dashboard so the two pages can never disagree), plus a 30-day "new Pro
    subscriptions" trend and a fuller recent-subscribers list.
    """
    metrics = compute_subscription_metrics(recent_limit=20)

    # New paying Pro subscriptions per day, last 30 days - real data (each
    # point is subscriptions whose current_period_start falls that day),
    # not a projection. Complimentary grants are excluded on purpose: they
    # don't represent revenue, and mixing them in would make this chart lie
    # about growth the same way counting comps in MRR would.
    new_pro_series = _daily_series(
        Subscription.objects.filter(is_complimentary=False, current_period_start__isnull=False),
        'current_period_start', 30,
    )

    context = _admin_context(request, 'Revenue')
    context.update({
        'subscriptions': metrics,
        'new_pro_growth': {
            'series': new_pro_series,
            'points': _svg_points(new_pro_series),
            'total': int(sum(p['value'] for p in new_pro_series)),
        },
    })
    return render(request, 'admin/revenue.html', context)


def system_health_view(request):
    """
    Lightweight, safe-by-default health checks - never displays a secret
    value (API key, DB password, etc.), only whether each dependency is
    configured and/or reachable right now. Deliberately does NOT make a
    live call to Groq (that costs a request against your quota on every
    admin page load) - just reports whether GROQ_API_KEY is set, which is
    exactly the thing worth checking first if the AI assistant is
    returning "service unavailable" (see apps/ai/views.py - that's the
    #1 cause of that message locally).
    """
    from django.conf import settings

    checks = []

    # Database
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        checks.append({'label': 'Database', 'sub': connection.settings_dict.get('ENGINE', '').rsplit('.', 1)[-1], 'ok': True})
    except Exception as e:
        checks.append({'label': 'Database', 'sub': str(e)[:120], 'ok': False})

    # Cache (Redis if REDIS_URL is set, otherwise the locmem fallback - see
    # settings.py - either way this proves the configured backend actually
    # works, not just that it's configured)
    try:
        cache_key = '_viq_health_check'
        cache.set(cache_key, 'ok', timeout=5)
        cache_ok = cache.get(cache_key) == 'ok'
        using_redis = bool(getattr(settings, 'REDIS_URL', ''))
        checks.append({'label': 'Cache', 'sub': 'Redis' if using_redis else 'In-memory (single process only)', 'ok': cache_ok})
    except Exception as e:
        checks.append({'label': 'Cache', 'sub': str(e)[:120], 'ok': False})

    # Celery workers - a genuinely "off" result here is normal in local dev
    # (no worker running) and not necessarily a problem, so this is styled
    # as neutral/off rather than a hard failure in the template.
    celery_status = 'unknown'
    try:
        from vendoriq.celery import app as celery_app
        pong = celery_app.control.ping(timeout=1.0)
        celery_status = 'ok' if pong else 'off'
    except Exception:
        celery_status = 'off'

    # Config presence - never the value itself, just whether it's set
    groq_configured = bool(getattr(settings, 'GROQ_API_KEY', ''))
    sentry_configured = bool(getattr(settings, 'SENTRY_DSN', ''))
    email_configured = getattr(settings, 'EMAIL_BACKEND', '').endswith('smtp.EmailBackend')

    config_checks = [
        {
            'label': 'AI assistant (Groq)', 'ok': groq_configured,
            'sub': f'Configured \u2014 using {settings.GROQ_MODEL}' if groq_configured else 'GROQ_API_KEY not set',
            'hint': '' if groq_configured else 'The AI Assistant page will show "AI service not configured" until this is set.',
        },
        {
            'label': 'Error monitoring (Sentry)', 'ok': sentry_configured, 'optional': True,
            'sub': 'Configured' if sentry_configured else 'Optional - SENTRY_DSN not set',
        },
        {
            'label': 'Outbound email', 'ok': email_configured, 'optional': True,
            'sub': 'SMTP configured' if email_configured else 'Printing to console (EMAIL_HOST not set)',
        },
    ]

    context = _admin_context(request, 'System Health')
    context.update({
        'checks': checks,
        'celery_status': celery_status,
        'config_checks': config_checks,
        'checked_at': timezone.now(),
    })
    return render(request, 'admin/system_health.html', context)


def support_view(request):
    """
    Honest placeholder, matching the same "Planned" convention used
    elsewhere (see templates/admin/index.html) rather than faking a
    ticket queue with no real tickets behind it. If/when a real support
    system is built, this becomes a real queryset-backed page the same
    way Revenue was built once Subscription existed.
    """
    return render(request, 'admin/support.html', _admin_context(request, 'Support'))


def settings_view(request):
    """
    Read-only view of the current Free/Pro plan configuration
    (apps/billing/plans.py) plus the current free trial length and Pro
    price - the same data the pricing/upgrade UI in the app itself reads,
    so support staff can see exactly what a Free, Trial, or Pro account
    gets without reading source code.

    Plan LIMITS/features are code-driven (plans.py) and genuinely can't be
    safely changed from a form here without a redeploy - this page tells
    you what to change and where, rather than pretending to change it for
    you. Price and trial length are the two exceptions: both are shown
    here for visibility, but are actually edited from Django Admin under
    Revenue & Billing (Pro plan price / Free trial length) - real DB-backed
    settings that take effect immediately, no redeploy. See
    get_pro_price_ngn() and get_trial_period_days() in
    apps/billing/models.py.
    """
    from apps.billing.plans import get_plan_config

    context = _admin_context(request, 'Plans & Settings')
    context.update({
        # Built via get_plan_config() per plan (not the raw PLANS dict)
        # specifically so Pro's price_ngn here is the live value, not
        # whatever was baked in at process startup.
        'plans': {code: get_plan_config(code) for code in PLANS},
        'pro_price': get_pro_price_ngn(),
        'trial_period_days': get_trial_period_days(),
    })
    return render(request, 'admin/plan_settings.html', context)
