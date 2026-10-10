import LegalLayout from '../../components/legal/LegalLayout'
import { Section, P, UL } from '../../components/legal/LegalContent'
import { BUSINESS } from '../../lib/businessInfo'

/**
 * DRAFT content - reflects what this codebase actually collects and sends
 * to third parties as of when this was written (see CHANGES.md / the
 * conversation that produced this file for the data inventory). It is NOT
 * legal advice and has not been reviewed by a lawyer. Have one review this
 * before you rely on it, especially the NDPA/GDPR framing and anything
 * involving a Data Protection Officer requirement.
 */
export default function PrivacyPolicyPage() {
  return (
    <LegalLayout title="Privacy Policy">
      <P>
        This Privacy Policy explains what personal data {BUSINESS.tradingName} ("we", "us") collects when you use
        our app, why we collect it, who we share it with, and the choices and rights you have over it. It applies
        to the {BUSINESS.tradingName} web and mobile app and covers you as a business owner/staff member using
        {' '}{BUSINESS.tradingName} ("you", the "user"), as well as the customer-facing data you as a merchant enter
        about your own customers (e.g. on invoices) while using the app.
      </P>

      <Section title="1. Who we are">
        <P>
          {BUSINESS.tradingName} is operated by {BUSINESS.legalName}
          {BUSINESS.cacNumber ? <> (CAC RC {BUSINESS.cacNumber})</> : null}, {BUSINESS.address}. You can reach us at{' '}
          <a href={`mailto:${BUSINESS.supportEmail}`} className="text-brand-500 hover:underline">{BUSINESS.supportEmail}</a>.
        </P>
      </Section>

      <Section title="2. What we collect">
        <P><strong className="text-slate-text">Account data.</strong> When you sign up, we collect your name, email address, and (optionally) phone number. If you sign up with "Continue with Google," Google shares your name and email with us instead of you typing them in. We store your password only in irreversibly hashed form - we cannot see or recover your actual password.</P>
        <P><strong className="text-slate-text">Business data you enter.</strong> Store names and locations, products, prices and stock levels, sales records, expenses, invoices (including any customer name/contact details you choose to put on an invoice), and staff you invite to a store. This is your business's own data - we process it on your behalf, not for our own purposes.</P>
        <P><strong className="text-slate-text">AI Assistant conversations.</strong> If you use the AI Assistant, your messages and the store data used to answer them (e.g. recent sales figures) are sent to our AI provider (currently Groq, or OpenAI if we switch providers - see Section 5) to generate a response, and the conversation is saved so it's there when you come back.</P>
        <P><strong className="text-slate-text">Payment data.</strong> If you upgrade to a paid plan, your payment is handled entirely by Paystack. We never see or store your card number - we only receive a transaction reference and a success/failure status from Paystack.</P>
        <P><strong className="text-slate-text">Login &amp; security logs.</strong> For security and fraud-prevention purposes, we log login attempts: timestamp, success/failure, IP address, and device/browser/OS type.</P>
        <P><strong className="text-slate-text">Sign-in cookie and local device storage.</strong> To keep you signed in we set one strictly necessary, HttpOnly cookie (it cannot be read by scripts on the page). Your theme preference (light/dark), your active store and a couple of show/hide display preferences are kept in your browser's local storage - see our <a href="/legal/cookies" className="text-brand-500 hover:underline">Cookie Policy</a>.</P>
        <P><strong className="text-slate-text">Usage analytics.</strong> We record how the app is used - for example which pages are opened and whether a sale, product, sign-up, verification, trial or upgrade was completed - using PostHog, from your browser and from our servers. We identify you only by a random account ID, plus your role and plan; for purchases we record the plan, billing cycle and amount. We do not send your name, email, phone number, customers, product names or barcodes, and we do not record your screen or use advertising cookies. This is part of how we run and improve the service (our legitimate interest); to object, contact us at the address above.</P>
        <P><strong className="text-slate-text">Error/crash data.</strong> If enabled, technical error reports (what broke, not your personal data) may be sent to our error-monitoring provider, Sentry, to help us fix bugs - see Section 5.</P>
      </Section>

      <Section title="3. Why we collect it (legal basis)">
        <UL>
          <li><strong className="text-slate-text">To provide the service</strong> you signed up for - account creation, running your store's dashboard, generating invoices, etc. (performance of a contract with you.)</li>
          <li><strong className="text-slate-text">To process payments</strong> for a paid plan (performance of a contract, and compliance with payment-related obligations.)</li>
          <li><strong className="text-slate-text">To keep the service secure</strong> - login logs help us detect and investigate suspicious account activity (our legitimate interest in security, balanced against your privacy.)</li>
          <li><strong className="text-slate-text">To communicate with you</strong> - e.g. sending an invoice you created to your customer at your request, or telling you about a change to these policies.</li>
          <li><strong className="text-slate-text">To understand and improve the service</strong> - anonymous usage analytics (our legitimate interest).</li>
          <li><strong className="text-slate-text">With your consent</strong> - where a specific action asks for it, such as agreeing to these policies at signup, or an upgrade payment.</li>
        </UL>
      </Section>

      <Section title="4. Data minimization">
        <P>We only ask for what the app actually needs to function: name, email, and an optional phone number at signup - nothing else. We don't collect government ID numbers, physical addresses, or any information unrelated to running your store through this app.</P>
      </Section>

      <Section title="5. Who we share data with">
        <P>We don't sell your data. We share it only with the service providers that help us run the app (our "processors"), and only what each one needs to do its job:</P>
        <UL>
          <li><strong className="text-slate-text">Paystack</strong> - payment processing. Paystack receives your email and the transaction amount; your card details go directly to Paystack, never to us.</li>
          <li><strong className="text-slate-text">Groq and/or OpenAI</strong> - whichever AI provider is currently configured (an administrator can switch this) receives your AI Assistant messages and relevant store data to generate a response.</li>
          <li><strong className="text-slate-text">Google</strong> - if you use "Continue with Google," Google authenticates you and shares your name/email with us.</li>
          <li><strong className="text-slate-text">PostHog</strong> - receives the usage events described in Section 2 (browser events are routed through our own domain). Never receives your name, contact details or business records.</li>
          <li><strong className="text-slate-text">Sentry</strong> (optional, if enabled) - receives technical error reports for debugging. Not configured to include your personal data by default.</li>
          <li><strong className="text-slate-text">Email delivery provider</strong> - used to send invoice emails and account-related emails on your behalf.</li>
        </UL>
        <P>We may also disclose data if required by law, or to protect our rights, users, or the public.</P>
      </Section>

      <Section title="6. How long we keep it">
        <P>We keep your account and business data for as long as your account is active. If you delete your account or a store, we remove the associated data within a reasonable period, except where we're required to keep certain records for longer (e.g. transaction records for tax/accounting purposes). Login/security logs are kept for a limited period for security purposes and are not retained indefinitely.</P>
      </Section>

      <Section title="7. Your rights">
        <P>Depending on where you're located, you may have rights to access, correct, export, or delete your personal data, and to object to or restrict certain processing. Nigerian users have these rights under the Nigeria Data Protection Act, 2023; users elsewhere may have equivalent rights under their own local law (e.g. the GDPR for EU/UK users). To exercise any of these, contact us at {BUSINESS.supportEmail}{BUSINESS.dataProtectionContact ? <> or our data protection contact, {BUSINESS.dataProtectionContact}</> : null}. You can also delete your own account data directly from the app's Profile page, where available.</P>
      </Section>

      <Section title="8. Children">
        <P>{BUSINESS.tradingName} is a business tool and is not directed at, or knowingly used to collect data from, children. If you believe a child has provided us with personal data, contact us and we will remove it.</P>
      </Section>

      <Section title="9. Changes to this policy">
        <P>If we make a material change to this policy, we'll update the "Last updated" date above and, where appropriate, notify you in-app or by email.</P>
      </Section>
    </LegalLayout>
  )
}
