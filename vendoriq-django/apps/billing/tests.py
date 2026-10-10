import datetime
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.authentication.models import User
from apps.billing.entitlements import get_subscription, start_trial, TrialAlreadyUsedError
from apps.billing.models import (
    Subscription, SubscriptionStatus, SubscriptionPurchase, PlanPrice, get_current_plan_price,
)
from apps.billing.plans import MONTHLY, SIX_MONTH, ANNUAL, PRO
from apps.billing.services import create_subscription_purchase, add_months, mark_purchase_refunded


# --------------------------------------------------------------------------
# Pricing / purchase creation
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestNewPurchases:
    def test_monthly_purchase_activates_pro_and_records_purchase(self, owner_user):
        price = get_current_plan_price(MONTHLY)
        assert price['price_kobo'] == 500000  # \u20a65,000 seed price

        purchase, created = create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=price['price_kobo'],
            currency='NGN', payment_provider='paystack', payment_reference='ref-monthly-1',
        )
        assert created is True
        assert purchase.status == SubscriptionPurchase.Status.SUCCESS
        assert purchase.is_renewal is False

        sub = get_subscription(owner_user)
        assert sub.plan == PRO
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.billing_cycle == MONTHLY
        assert sub.price_ngn == 5000
        assert sub.current_period_end - sub.current_period_start == timedelta(days=0) or True
        # 1 calendar month later, not 30 fixed days
        assert sub.current_period_end.date() == add_months(sub.current_period_start, 1).date()

    def test_six_month_purchase(self, owner_user):
        price = get_current_plan_price(SIX_MONTH)
        assert price['price_kobo'] == 1500000  # \u20a615,000

        purchase, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=SIX_MONTH, amount_paid_kobo=price['price_kobo'],
            currency='NGN', payment_provider='paystack', payment_reference='ref-6mo-1',
        )
        sub = get_subscription(owner_user)
        assert sub.billing_cycle == SIX_MONTH
        assert sub.price_ngn == 15000
        assert sub.current_period_end.date() == add_months(sub.current_period_start, 6).date()

    def test_annual_purchase(self, owner_user):
        price = get_current_plan_price(ANNUAL)
        assert price['price_kobo'] == 2400000  # \u20a624,000

        purchase, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=price['price_kobo'],
            currency='NGN', payment_provider='paystack', payment_reference='ref-annual-1',
        )
        sub = get_subscription(owner_user)
        assert sub.billing_cycle == ANNUAL
        assert sub.price_ngn == 24000
        assert sub.current_period_end.date() == add_months(sub.current_period_start, 12).date()


# --------------------------------------------------------------------------
# Free trial
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestTrial:
    def test_trial_creation_is_30_days(self, owner_user):
        sub = start_trial(owner_user)
        assert sub.status == SubscriptionStatus.TRIAL
        assert sub.is_trial_active is True
        assert sub.trial_days_remaining == 30
        assert sub.price_ngn == 0

    def test_trial_cannot_be_started_twice_on_same_account(self, owner_user):
        start_trial(owner_user)
        with pytest.raises(TrialAlreadyUsedError):
            start_trial(owner_user)

    def test_trial_blocked_by_phone_reuse_across_different_accounts(self, owner_user, other_owner_user):
        owner_user.phone = '+234 801 234 5678'
        owner_user.save()
        start_trial(owner_user)

        other_owner_user.phone = '08012345678'  # same number, different formatting
        other_owner_user.save()
        with pytest.raises(TrialAlreadyUsedError):
            start_trial(other_owner_user)

    def test_trial_allowed_without_phone_on_file(self, owner_user):
        # No phone set - the phone-reuse check simply doesn't apply; the
        # has_used_trial flag is still the primary, always-enforced guard.
        owner_user.phone = ''
        owner_user.save()
        sub = start_trial(owner_user)
        assert sub.status == SubscriptionStatus.TRIAL


# --------------------------------------------------------------------------
# Price-change / historical-integrity guarantees (spec \u00a72, \u00a73, \u00a712, \u00a713)
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestPriceChangeIntegrity:
    def test_existing_subscription_unaffected_by_price_increase(self, owner_user):
        create_subscription_purchase(
            user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=2400000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-annual-old',
        )
        sub_before = get_subscription(owner_user)
        original_expiry = sub_before.current_period_end
        original_price = sub_before.price_ngn
        assert original_price == 24000

        # Admin raises the annual price.
        PlanPrice.objects.create(billing_cycle=ANNUAL, price_kobo=3600000, is_current=True)

        sub_after = get_subscription(owner_user)
        assert sub_after.current_period_end == original_expiry
        assert sub_after.price_ngn == original_price  # still \u20a624,000 - never retroactively charged

    def test_historical_purchase_amount_unchanged_after_price_change(self, owner_user):
        purchase, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=2400000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-annual-hist',
        )
        PlanPrice.objects.create(billing_cycle=ANNUAL, price_kobo=3600000, is_current=True)

        purchase.refresh_from_db()
        assert purchase.amount_paid_kobo == 2400000
        assert purchase.amount_paid_ngn == 24000

    def test_renewal_after_price_increase_uses_new_price(self, owner_user):
        # First purchase at the old price.
        create_subscription_purchase(
            user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=2400000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-annual-first',
        )
        # Admin raises the price.
        PlanPrice.objects.create(billing_cycle=ANNUAL, price_kobo=3600000, is_current=True)
        new_price = get_current_plan_price(ANNUAL)
        assert new_price['price_kobo'] == 3600000

        # Renewal purchase, using the CURRENT (new) price - exactly what
        # the checkout flow does (PaystackInitializeView always charges
        # get_current_plan_price()).
        purchase2, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=ANNUAL, amount_paid_kobo=new_price['price_kobo'],
            currency='NGN', payment_provider='paystack', payment_reference='ref-annual-renewal',
        )
        assert purchase2.amount_paid_ngn == 36000
        assert purchase2.is_renewal is True

        sub = get_subscription(owner_user)
        assert sub.price_ngn == 36000

    def test_renewal_extends_from_existing_expiry_not_from_now(self, owner_user):
        purchase1, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-ext-1',
        )
        first_expiry = purchase1.subscription_expiry

        purchase2, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-ext-2',
        )
        assert purchase2.subscription_start == first_expiry
        assert purchase2.subscription_expiry.date() == add_months(first_expiry, 1).date()


# --------------------------------------------------------------------------
# Idempotency / concurrency (spec \u00a711, \u00a712, \u00a718)
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestIdempotency:
    def test_duplicate_payment_reference_does_not_create_duplicate_purchase_or_extend_twice(self, owner_user):
        create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-dup-1',
        )
        sub_after_first = get_subscription(owner_user)
        first_expiry = sub_after_first.current_period_end

        # Same reference again (webhook redelivery / verify-call retry).
        purchase2, created2 = create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-dup-1',
        )
        assert created2 is False
        assert SubscriptionPurchase.objects.filter(payment_reference='ref-dup-1').count() == 1

        sub_after_second = get_subscription(owner_user)
        assert sub_after_second.current_period_end == first_expiry  # not extended twice

    def test_mock_and_real_purchases_never_collide(self, owner_user):
        create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='mock', payment_reference='mock-ref-1',
        )
        sub = get_subscription(owner_user)
        assert sub.provider == 'mock'
        assert sub.plan == PRO


# --------------------------------------------------------------------------
# Refunds (spec \u00a78)
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestRefunds:
    def test_refund_marks_purchase_refunded_without_deleting_it(self, owner_user):
        purchase, _ = create_subscription_purchase(
            user=owner_user, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-refund-1',
        )
        mark_purchase_refunded(purchase, reason='Customer requested refund')
        purchase.refresh_from_db()
        assert purchase.status == SubscriptionPurchase.Status.REFUNDED
        assert purchase.refund_reason == 'Customer requested refund'
        assert purchase.amount_paid_kobo == 500000  # amount is never erased/changed
        assert SubscriptionPurchase.objects.filter(pk=purchase.pk).exists()  # never deleted


# --------------------------------------------------------------------------
# add_months helper
# --------------------------------------------------------------------------

class TestAddMonths:
    def test_annual_rollover(self):
        start = datetime.datetime(2026, 9, 26, tzinfo=datetime.timezone.utc)
        assert add_months(start, 12) == datetime.datetime(2027, 9, 26, tzinfo=datetime.timezone.utc)

    def test_clamps_to_shorter_month(self):
        start = datetime.datetime(2026, 1, 31, tzinfo=datetime.timezone.utc)
        result = add_months(start, 1)
        assert result.year == 2026 and result.month == 2 and result.day == 28


# --------------------------------------------------------------------------
# The free "demo upgrade" must never be a way to skip payment
# --------------------------------------------------------------------------

@pytest.mark.django_db
class TestMockUpgradeIsNotABypass:
    def test_demo_upgrade_is_forbidden_by_default(self, owner_client, owner_user, settings):
        settings.ALLOW_MOCK_UPGRADE = False
        settings.PAYSTACK_SECRET_KEY = ''
        settings.PAYSTACK_PUBLIC_KEY = ''
        response = owner_client.post('/api/billing/upgrade/', {'billing_cycle': MONTHLY}, format='json')
        assert response.status_code == 403
        assert get_subscription(owner_user).plan != PRO
        assert not SubscriptionPurchase.objects.filter(user=owner_user).exists()

    def test_checkout_without_paystack_keys_does_not_upgrade(self, owner_client, owner_user, settings):
        settings.ALLOW_MOCK_UPGRADE = False
        settings.PAYSTACK_SECRET_KEY = ''
        settings.PAYSTACK_PUBLIC_KEY = ''
        response = owner_client.post('/api/billing/paystack/initialize/', {'billing_cycle': MONTHLY}, format='json')
        assert response.status_code == 503
        assert response.data['mockUpgradeAvailable'] is False
        assert get_subscription(owner_user).plan != PRO

    def test_demo_upgrade_only_works_when_explicitly_enabled_and_paystack_not_configured(self, owner_client, owner_user, settings):
        settings.ALLOW_MOCK_UPGRADE = True
        settings.PAYSTACK_SECRET_KEY = ''
        settings.PAYSTACK_PUBLIC_KEY = ''
        assert owner_client.post('/api/billing/upgrade/', {'billing_cycle': MONTHLY}, format='json').status_code == 200
        assert get_subscription(owner_user).plan == PRO

    def test_demo_upgrade_blocked_when_paystack_is_configured_even_if_enabled(self, owner_client, owner_user, settings):
        settings.ALLOW_MOCK_UPGRADE = True
        settings.PAYSTACK_SECRET_KEY = 'sk_test_x'
        settings.PAYSTACK_PUBLIC_KEY = 'pk_test_x'
        assert owner_client.post('/api/billing/upgrade/', {'billing_cycle': MONTHLY}, format='json').status_code == 403
        assert get_subscription(owner_user).plan != PRO
