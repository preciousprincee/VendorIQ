import { Link } from 'react-router-dom'
import { BUSINESS } from '../../lib/businessInfo'

/**
 * Small business-identity + legal-links footer. Shown on the public
 * Welcome page (full) and the (authenticated) Profile page (compact) -
 * the two places someone is most likely to be looking for "who actually
 * runs this app" or "where's the privacy policy."
 *
 * Displaying real business details (legal name, registration number,
 * address) is itself a consumer-protection expectation in a lot of
 * jurisdictions, not just a nice-to-have - see the note in businessInfo.js.
 * That's why it's kept on the public Welcome page; on the in-app Profile
 * page (`compact`) it's trimmed to just the legal links, since a
 * logged-in user has already seen it once and a long block of legal text
 * at the bottom of every profile visit is more clutter than disclosure.
 */
export default function BusinessFooter({ compact = false }) {
  return (
    <footer className="text-center pt-6 mt-2">
      <div className="flex items-center justify-center flex-wrap gap-x-3 gap-y-1 text-xs">
        <Link to="/legal/privacy" className="text-slate-dim hover:text-slate-muted">Privacy Policy</Link>
        <span className="text-slate-dim">&middot;</span>
        <Link to="/legal/terms" className="text-slate-dim hover:text-slate-muted">Terms &amp; Conditions</Link>
        <span className="text-slate-dim">&middot;</span>
        <Link to="/legal/cookies" className="text-slate-dim hover:text-slate-muted">Cookie Policy</Link>
        <span className="text-slate-dim">&middot;</span>
        <Link to="/legal/refunds" className="text-slate-dim hover:text-slate-muted">Refund Policy</Link>
      </div>
      {!compact && (
        <p className="text-[11px] text-slate-dim mt-3 leading-relaxed">
          {BUSINESS.tradingName} is operated by {BUSINESS.legalName}
          {BUSINESS.cacNumber ? <> &middot; CAC RC {BUSINESS.cacNumber}</> : null}
          <br />
          {BUSINESS.address}
          {' '}&middot;{' '}
          <a href={`mailto:${BUSINESS.supportEmail}`} className="hover:text-slate-muted">{BUSINESS.supportEmail}</a>
        </p>
      )}
    </footer>
  )
}
