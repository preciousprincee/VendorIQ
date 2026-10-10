from rest_framework import serializers
from .models import Subscription, SubscriptionStatus, get_trial_period_days, get_plan_pricing_catalog
from .plans import PRO, get_plan_config, public_plan_catalog
from .entitlements import get_usage


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    The full "where does my account stand" payload for
    Settings > Subscription/Billing - current plan/billing-cycle,
    status/period dates, live usage, trial state, and the full pricing +
    feature catalog so the frontend never hardcodes a second copy of
    prices, limits, or features.
    """
    plan = serializers.CharField(source='effective_plan', read_only=True)
    planConfig = serializers.SerializerMethodField()
    billingCycle = serializers.CharField(source='billing_cycle', read_only=True)
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
    # touched billing - the CURRENT trial length, live-editable from Django
    # Admin. See apps/billing/models.py::get_trial_period_days().
    trialPeriodDays = serializers.SerializerMethodField()
    # What THIS subscriber is actually paying, locked in at their last
    # purchase - never "today's price" (see Subscription.price_ngn).
    amountPaidNgn = serializers.IntegerField(source='price_ngn', read_only=True)
    usage = serializers.SerializerMethodField()
    plans = serializers.SerializerMethodField()
    pricing = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            'plan', 'planConfig', 'billingCycle', 'status', 'currentPeriodStart', 'currentPeriodEnd',
            'cancelAtPeriodEnd', 'isProActive', 'isTrialActive', 'trialDaysRemaining',
            'hasUsedTrial', 'trialPeriodDays', 'amountPaidNgn', 'usage', 'plans', 'pricing',
        ]

    def get_planConfig(self, obj):
        cfg = get_plan_config(obj.effective_plan)
        return {
            'name': cfg['name'],
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

    def get_pricing(self, obj):
        return get_plan_pricing_catalog()
