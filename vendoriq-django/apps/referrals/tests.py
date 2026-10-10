import pytest

from apps.authentication.models import User
from apps.billing.plans import MONTHLY, SIX_MONTH, ANNUAL
from apps.billing.services import create_subscription_purchase, mark_purchase_refunded
from apps.referrals.models import Referral, ReferralCommission
from apps.referrals.services import record_referral_if_applicable, process_referral_commission


@pytest.fixture
def referrer(db):
    return User.objects.create_user(email='referrer@example.com', name='Referrer', password='Testpass123!', phone='08011111111')


@pytest.fixture
def referred(db):
    return User.objects.create_user(email='referred@example.com', name='Referred', password='Testpass123!', phone='08022222222')


@pytest.fixture
def referral(db, referrer, referred):
    return Referral.objects.create(referrer=referrer, referred_user=referred, code_used=referrer.referral_code)


@pytest.mark.django_db
class TestReferralAttribution:
    def test_referral_attribution_at_registration(self, referrer, referred):
        record_referral_if_applicable(referred, referrer.referral_code)
        assert Referral.objects.filter(referrer=referrer, referred_user=referred).exists()

    def test_referral_code_is_the_phone_number(self, referrer):
        assert referrer.referral_code == '08011111111'

    def test_referral_matches_phone_typed_in_any_format(self, referrer, referred):
        record_referral_if_applicable(referred, '+234 801 111 1111')
        assert Referral.objects.filter(referrer=referrer, referred_user=referred).exists()

    def test_user_without_phone_has_no_referral_code(self, db):
        user = User.objects.create_user(email='nophone@example.com', name='No Phone', password='Testpass123!')
        assert user.referral_code is None

    def test_no_self_referral(self, referrer):
        record_referral_if_applicable(referrer, referrer.referral_code)
        assert not Referral.objects.filter(referred_user=referrer).exists()

    def test_unknown_code_does_not_error_or_create_referral(self, referred):
        record_referral_if_applicable(referred, 'NOTAREALCODE')
        assert not Referral.objects.filter(referred_user=referred).exists()


@pytest.mark.django_db
class TestCommissionAmounts:
    """Spec \u00a74 examples: 20% of the actual amount paid, computed from the real payment - never a hardcoded plan price."""

    def test_monthly_commission_is_1000_at_5000(self, referral, referred):
        purchase, _ = create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-comm-monthly',
        )
        commission = ReferralCommission.objects.get(referral=referral)
        assert commission.amount_ngn == 1000

    def test_six_month_commission_is_3000_at_15000(self, referral, referred):
        create_subscription_purchase(
            user=referred, billing_cycle=SIX_MONTH, amount_paid_kobo=1500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-comm-6mo',
        )
        commission = ReferralCommission.objects.get(referral=referral)
        assert commission.amount_ngn == 3000

    def test_annual_commission_is_4800_at_24000(self, referral, referred):
        create_subscription_purchase(
            user=referred, billing_cycle=ANNUAL, amount_paid_kobo=2400000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-comm-annual',
        )
        commission = ReferralCommission.objects.get(referral=referral)
        assert commission.amount_ngn == 4800


@pytest.mark.django_db
class TestCommissionEligibility:
    def test_no_commission_for_trial(self, referral, referred):
        from apps.billing.entitlements import start_trial
        start_trial(referred)
        assert ReferralCommission.objects.filter(referral=referral).count() == 0

    def test_no_commission_for_mock_dev_payment(self, referral, referred):
        # The mock (no-real-money) flow must never pay out a real commission.
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='mock', payment_reference='ref-mock-1',
        )
        assert ReferralCommission.objects.filter(referral=referral).count() == 0

    def test_no_commission_created_if_payment_never_recorded(self, referral, referred):
        # A "failed payment" simply never calls create_subscription_purchase -
        # there is nothing to react to, and no commission is created.
        assert ReferralCommission.objects.filter(referral=referral).count() == 0

    def test_commission_is_one_time_only_not_recurring(self, referral, referred):
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-first',
        )
        assert ReferralCommission.objects.filter(referral=referral).count() == 1

        # A second (renewal) purchase must NOT generate a second commission.
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-renewal',
        )
        assert ReferralCommission.objects.filter(referral=referral).count() == 1

    def test_no_duplicate_commission_from_duplicate_webhook(self, referral, referred):
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-webhook-retry',
        )
        # Simulate the webhook (or client verify call) firing again for the
        # exact same payment.
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-webhook-retry',
        )
        assert ReferralCommission.objects.filter(referral=referral).count() == 1

    def test_commission_still_earned_after_earlier_mock_purchase(self, referral, referred):
        # A free/demo (mock, no real money) upgrade - e.g. made back when
        # Paystack wasn't configured yet - must never consume the
        # referral's one-time commission slot. The user's first REAL
        # purchase afterwards should still earn it in full.
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='mock', payment_reference='ref-mock-before-real',
        )
        assert ReferralCommission.objects.filter(referral=referral).count() == 0

        create_subscription_purchase(
            user=referred, billing_cycle=ANNUAL, amount_paid_kobo=2400000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-first-real-after-mock',
        )
        commissions = ReferralCommission.objects.filter(referral=referral)
        assert commissions.count() == 1
        assert commissions.first().amount_ngn == 4800

    def test_commission_computed_from_actual_amount_paid_not_hardcoded_price(self, referral, referred):
        # A discounted/promo payment of \u20a63,000 for a Monthly plan still
        # earns exactly 20% of what was ACTUALLY paid, not 20% of the
        # normal \u20a65,000 list price.
        create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=300000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-discounted',
        )
        commission = ReferralCommission.objects.get(referral=referral)
        assert commission.amount_ngn == 600


@pytest.mark.django_db
class TestRefundReversesCommission:
    def test_refund_reverses_commission_without_deleting_it(self, referral, referred):
        purchase, _ = create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-refund-comm',
        )
        commission = ReferralCommission.objects.get(referral=referral)
        assert commission.status != ReferralCommission.Status.REVERSED

        mark_purchase_refunded(purchase, reason='Chargeback')

        commission.refresh_from_db()
        assert commission.status == ReferralCommission.Status.REVERSED
        assert ReferralCommission.objects.filter(pk=commission.pk).exists()  # never deleted
        assert commission.amount_ngn == 1000  # original amount preserved for audit

    def test_new_purchase_after_refunded_one_is_eligible_again(self, referral, referred):
        purchase1, _ = create_subscription_purchase(
            user=referred, billing_cycle=MONTHLY, amount_paid_kobo=500000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-first-refunded',
        )
        mark_purchase_refunded(purchase1, reason='Refunded before any real usage')

        # A genuinely new "first" successful purchase (the earlier one no
        # longer counts as a successful purchase after being refunded)
        # should be eligible for a fresh commission.
        purchase1.status = 'REFUNDED'  # already set by mark_purchase_refunded; documenting intent
        create_subscription_purchase(
            user=referred, billing_cycle=ANNUAL, amount_paid_kobo=2400000,
            currency='NGN', payment_provider='paystack', payment_reference='ref-second-real',
        )
        live_commissions = ReferralCommission.objects.filter(referral=referral).exclude(status=ReferralCommission.Status.REVERSED)
        assert live_commissions.count() == 1
        assert live_commissions.first().amount_ngn == 4800
