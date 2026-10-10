import LegalLayout from '../../components/legal/LegalLayout'
import { Section, P, UL } from '../../components/legal/LegalContent'
import { BUSINESS } from '../../lib/businessInfo'

/**
 * DRAFT content, written to match what the code actually does:
 *   - ONE first-party cookie, `viq_refresh` (HttpOnly, Secure, SameSite=Lax, path /api/auth/): the sign-in
 *     session. Strictly necessary.
 *   - localStorage for the session hint, active store, theme and display preferences (strictly necessary)
 *     and PostHog's anonymous id (analytics; always on, no opt-in).
 * PostHog is configured with localStorage persistence, so it sets no cookies. If that, or the cookie above,
 * ever changes, this page must change with it.
 */
export default function CookiePolicyPage() {
  return (
    <LegalLayout title="Cookie Policy">
      <P>
        This page explains what {BUSINESS.tradingName} stores on your device, and why. We don't use advertising
        cookies or cross-site tracking.
      </P>

      <Section title="What we actually use">
        <P>{BUSINESS.tradingName} sets <strong className="text-slate-text">one cookie</strong> and keeps a small amount of information in your browser's local storage so the app works properly:</P>
        <UL>
          <li><strong className="text-slate-text">Sign-in cookie</strong> (<code>viq_refresh</code>) - keeps you signed in for up to 30 days. It is HttpOnly (scripts on the page cannot read it), Secure, and only sent to our sign-in endpoints. Removed when you sign out.</li>
          <li><strong className="text-slate-text">Who was signed in</strong> (local storage) - so the app can open and keep selling even without internet. It grants no access by itself.</li>
          <li><strong className="text-slate-text">Your active store</strong> - which store you were last working in.</li>
          <li><strong className="text-slate-text">Display preferences</strong> - light/dark theme, and whether you've chosen to hide profit or stock-value figures on screen.</li>
        </UL>
        <P>All of this is <strong className="text-slate-text">strictly necessary</strong> for the app to function as intended for you specifically - it isn't used to track you across other sites, build an advertising profile, or share data with ad networks.</P>
      </Section>

      <Section title="Usage analytics">
        <P>We use PostHog to record anonymous usage events (see our Privacy Policy). In your browser it keeps a random identifier in local storage - not in a cookie - and it is not used for advertising or cross-site tracking.</P>
      </Section>

      <Section title="Third parties that may set their own cookies">
        <UL>
          <li><strong className="text-slate-text">Paystack</strong> - when you make a payment, Paystack's own checkout may set cookies needed for fraud prevention and to process your transaction. This is governed by Paystack's own privacy/cookie policy, not ours.</li>
          <li><strong className="text-slate-text">Google Sign-In</strong> - if you use "Continue with Google," Google's sign-in widget may set its own cookies as part of authenticating you, governed by Google's policies.</li>
        </UL>
        <P>We don't control what these third parties do with their own cookies once you're interacting directly with their checkout/sign-in widgets.</P>
      </Section>

      <Section title="Consent">
        <P>The sign-in cookie and the local storage listed under "What we actually use" are strictly necessary. Usage analytics are not strictly necessary and are not switched off by a banner; they are anonymous (a random ID, never your name or contact details) and described in our Privacy Policy. If you object to them, contact us using the details in our Privacy Policy. We don't use advertising cookies or cross-site profiling.</P>
      </Section>

      <Section title="Managing local storage">
        <P>Using "Log out" in the app removes the sign-in cookie and your session data. You can also clear this site's cookies and local storage in your browser's settings; that simply logs you out and resets your display preferences - it won't affect the business data saved on our servers. Clearing ALL site data also deletes any offline sales that have not synced yet, so make sure they have synced first.</P>
      </Section>
    </LegalLayout>
  )
}
