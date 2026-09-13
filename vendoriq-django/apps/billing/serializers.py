from rest_framework import serializers
from .models import Subscription, SubscriptionStatus, get_trial_period_days
from .plans import PRO, get_plan_config, public_plan_catalog
from .entitlements import get_usage


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    The full "where does my account stand" payload for
    Settings > Subscription/Billing - current plan config (name/price/
    limits/features), status/period dates, live usage, trial state, and the
    full Free/Pro catalog so the frontend never hardcodes a second copy of
    prices or limits.
    """
    plan = serializers.CharField(source='effective_plan', read_only=True)
    planConfig = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    currentPeriodStart = serializers.DateTimeField(source='current_period_start', read_only=True)
    currentPeriodEnd = serializers.DateTimeField(source='current_period_end', read_only=True)
    cancelAtPeriodEnd = serializers.BooleanField(source='cancel_at_period_end', read_only=True)
    isProActive = serializers.BooleanField(source='is_pro_active', read_only=True)
    isTrialActive = serializers.BooleanField(source='is_trial_active', read_only=True)
    trialDaysRemaining = serializers.IntegerField(source='trial_days_remaining', read_only=True)
    hasUsedTrial = serializers.BooleanField(source='has_used_trial', read_only=True)
    # Always present (not just once a trial has started) so the frontend can
    # advertise "start your N-day free trial" before the person has ever
    # touched billing - this is the CURRENT trial length, live-editable
    # from Django Admin (Revenue & Billing > Free trial length), the same
    # value every account's trial is measured against. See
    # apps/billing/models.py::get_trial_period_days().
    trialPeriodDays = serializers.SerializerMethodField()
    usage = serializers.SerializerMethodField()
    plans = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            'plan', 'planConfig', 'status', 'currentPeriodStart', 'currentPeriodEnd',
            'cancelAtPeriodEnd', 'isProActive', 'isTrialActive', 'trialDaysRemaining',
            'hasUsedTrial', 'trialPeriodDays', 'usage', 'plans',
        ]

    def get_planConfig(self, obj):
        cfg = get_plan_config(obj.effective_plan)
        price = cfg['price_ngn']
        # If this account is an existing PAYING Pro subscriber, show what
        # THEY actually locked in (obj.price_ngn) rather than today's live
        # price - otherwise an admin raising the price would make an
        # existing subscriber's own Subscription page look like they're
        # suddenly being charged more, even though price_ngn (what
        # actually determines their MRR contribution - see
        # vendoriq/admin_dashboard.py) hasn't changed for them at all.
        # Trials and complimentary grants correctly keep showing the live
        # price here since neither has a real locked-in price to show
        # instead (both have price_ngn=0 - see models.py).
        if obj.effective_plan == PRO and obj.price_ngn and not obj.is_complimentary and obj.status != SubscriptionStatus.TRIAL:
            price = obj.price_ngn
        return {
            'name': cfg['name'],
            'priceNgn': price,
            'tagline': cfg['tagline'],
            'includes': cfg['includes'],
            'limits': {
                'maxStores': cfg['limits']['max_stores'],
                'maxProductsPerStore': cfg['limits']['max_products_per_store'],
                'maxUsersPerStore': cfg['limits']['max_users_per_store'],
                'maxTrendHistoryDays': cfg['limits']['max_trend_history_days'],
            },
            'features': cfg['features'],
        }

    def get_trialPeriodDays(self, obj):
        return get_trial_period_days()

    def get_usage(self, obj):
        return get_usage(obj.user)

    def get_plans(self, obj):
        return public_plan_catalog()
