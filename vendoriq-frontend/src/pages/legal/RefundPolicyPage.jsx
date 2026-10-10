import LegalLayout from '../../components/legal/LegalLayout'
import { Section, P, UL } from '../../components/legal/LegalContent'
import { BUSINESS } from '../../lib/businessInfo'

/**
 * DRAFT content - not legal advice. Nigeria-specific consumer-protection
 * rules (FCCPC) may impose requirements on refund policies beyond what's
 * drafted here (e.g. around clearly disclosing terms before payment,
 * cooling-off periods for certain transaction types) - have this reviewed
 * before relying on it. Deliberately doesn't hardcode the Pro plan price
 * or trial length since both are admin-editable (apps/billing/models.py) -
 * says "as shown at checkout" instead so this page can't silently go stale.
 */
export default function RefundPolicyPage() {
  return (
    <LegalLayout title="Refund Policy">
      <P>
        This policy covers payments for {BUSINESS.tradingName}'s paid Pro plan, processed via Paystack.
      </P>

      <Section title="Free trial">
        <P>Where a free trial is available (see your Subscription page for its current length), you can try the Pro plan's features before paying anything. If you don't want to continue, you can cancel before the trial ends and you will not be charged.</P>
      </Section>

      <Section title="Subscription billing">
        <P>The Pro plan is billed on a recurring basis (currently monthly) at the price shown at checkout. By completing a payment, you authorize that charge for the billing period it covers.</P>
      </Section>

      <Section title="Cancellations">
        <P>You can cancel your Pro subscription at any time from the Subscription page. Cancelling stops future billing - it takes effect at the end of your current paid period, and you keep Pro access until then. Cancelling does not retroactively refund the current period.</P>
      </Section>

      <Section title="Refunds">
        <P>Because a free trial is available to test the Pro plan before paying, and because you can cancel at any time to stop future charges, we generally do not offer refunds for a subscription period that has already started, except in the following cases:</P>
        <UL>
          <li>You were charged due to a proven technical error or duplicate charge on our or Paystack's part;</li>
          <li>You were charged after a cancellation that should have taken effect;</li>
          <li>Applicable consumer-protection law entitles you to a refund in your circumstances.</li>
        </UL>
        <P>To request a refund under one of these grounds, contact us at{' '}
          <a href={`mailto:${BUSINESS.supportEmail}`} className="text-brand-500 hover:underline">{BUSINESS.supportEmail}</a>{' '}
          with your account email and transaction reference. We'll review and respond within a reasonable time.
        </P>
      </Section>

      <Section title="How refunds are paid">
        <P>Approved refunds are issued back to the original payment method via Paystack, and may take a number of business days to reflect depending on your bank/card issuer.</P>
      </Section>

      <Section title="Downgrading">
        <P>You can downgrade to the Free plan at any time. Your business data isn't deleted when you downgrade - some Pro-only features and higher limits simply become unavailable until you upgrade again.</P>
      </Section>
    </LegalLayout>
  )
}
