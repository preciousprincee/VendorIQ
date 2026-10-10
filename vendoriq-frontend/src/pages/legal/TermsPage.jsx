import LegalLayout from '../../components/legal/LegalLayout'
import { Section, P, UL } from '../../components/legal/LegalContent'
import { BUSINESS } from '../../lib/businessInfo'

/**
 * DRAFT content - not legal advice, not reviewed by a lawyer. In
 * particular: the liability-cap and governing-law clauses are the kind of
 * thing that genuinely needs a qualified local lawyer's sign-off before
 * you rely on them, and the Pro plan price mentioned below should be kept
 * in sync with apps/billing/plans.py by hand (it isn't pulled dynamically here).
 */
export default function TermsPage() {
  return (
    <LegalLayout title="Terms & Conditions">
      <P>
        These Terms govern your use of {BUSINESS.tradingName} (the "Service"), operated by {BUSINESS.legalName}.
        By creating an account, you agree to these Terms. If you don't agree, please don't use the Service.
      </P>

      <Section title="1. The Service">
        <P>{BUSINESS.tradingName} is a business-management tool for small merchants covering inventory, sales, invoicing, expense tracking, and an AI assistant. It is provided on a Free plan and a paid Pro plan with additional features and higher limits - see the in-app Subscription page for current plan details and pricing.</P>
      </Section>

      <Section title="2. Your account">
        <UL>
          <li>You must provide accurate information when you register, and keep your password confidential.</li>
          <li>You're responsible for all activity under your account, including actions taken by staff you invite to a store.</li>
          <li>You must be legally able to enter into a contract to use the Service.</li>
        </UL>
      </Section>

      <Section title="3. Acceptable use">
        <P>You agree not to:</P>
        <UL>
          <li>Use the Service for any unlawful purpose, or to store or transmit data you don't have the right to;</li>
          <li>Attempt to gain unauthorized access to the Service, other users' accounts, or our systems;</li>
          <li>Reverse-engineer, resell, or misuse the Service beyond your own business's normal use of it;</li>
          <li>Use the AI Assistant to generate or request unlawful, harmful, or abusive content.</li>
        </UL>
      </Section>

      <Section title="4. Your data and content">
        <P>You retain ownership of the business data you enter (products, sales, invoices, customer details, etc.). You're responsible for the accuracy of that data and for having the right to enter any customer/third-party data you put into the Service (e.g. on an invoice). We process it on your behalf as described in our <a href="/legal/privacy" className="text-brand-500 hover:underline">Privacy Policy</a>.</P>
      </Section>

      <Section title="5. AI Assistant">
        <P>The AI Assistant uses a third-party AI model to answer questions about your store data. Its responses are generated automatically and may occasionally be inaccurate or incomplete - you should use your own judgment before relying on them for business decisions, and they do not constitute financial, tax, or legal advice.</P>
      </Section>

      <Section title="6. Payments, plans and refunds">
        <P>Paid plan payments are processed by Paystack. Fees are billed as shown at checkout. See our <a href="/legal/refunds" className="text-brand-500 hover:underline">Refund Policy</a> for how refunds and cancellations work.</P>
      </Section>

      <Section title="7. Availability">
        <P>We aim to keep the Service available and reliable, but we don't guarantee uninterrupted, error-free access. We may modify, suspend, or discontinue any part of the Service, with notice where reasonably possible.</P>
      </Section>

      <Section title="8. Termination">
        <P>You may stop using the Service and delete your account at any time. We may suspend or terminate your access if you materially breach these Terms, including the acceptable-use rules in Section 3.</P>
      </Section>

      <Section title="9. Disclaimers and limitation of liability">
        <P>The Service is provided "as is" without warranties of any kind, to the maximum extent permitted by law. To the maximum extent permitted by applicable law, {BUSINESS.legalName} will not be liable for indirect, incidental, or consequential damages arising from your use of the Service. Nothing in these Terms excludes liability that cannot be excluded under applicable law.</P>
      </Section>

      <Section title="10. Governing law">
        <P>These Terms are governed by the laws of the Federal Republic of Nigeria{BUSINESS.governingLawState ? <>, and subject to the courts of {BUSINESS.governingLawState}</> : null}. If you use the Service from another country, local consumer-protection laws that cannot be waived by contract may also apply to you.</P>
      </Section>

      <Section title="11. Changes to these Terms">
        <P>We may update these Terms from time to time. Continuing to use the Service after an update means you accept the revised Terms.</P>
      </Section>
    </LegalLayout>
  )
}
