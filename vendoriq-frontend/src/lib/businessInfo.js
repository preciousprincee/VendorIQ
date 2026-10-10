// Single source of truth for the business details shown across the legal
// pages (Privacy Policy, Terms, Cookie Policy, Refund Policy) and the
// footer. Fill these in once here - everything else imports from this file
// instead of hardcoding the business name/address/contact in four places.
//
// IMPORTANT: the values below are PLACEHOLDERS. Using placeholder legal
// identity details (a fake registration number, a fake address) in a live
// privacy policy or terms page is itself a legal risk - it needs to be
// accurate, not just present. Replace every [BRACKETED] value before this
// app is live for real users.
export const BUSINESS = {
  legalName: 'Vendoriq Technologies Ltd', // e.g. "Vendoriq Technologies Ltd" - as registered with CAC, not just a trading/brand name
  tradingName: 'VendorIQ',
  //cacNumber: '[CAC REGISTRATION NUMBER, IF REGISTERED]', // RC number from cac.gov.ng - if you're not yet incorporated, say so plainly instead of leaving this blank; operating as an unregistered business has its own implications (see FCCPC/CAC guidance)
  //address: '[REGISTERED/OPERATING ADDRESS, CITY, STATE, NIGERIA]',
  //supportEmail: '[support@yourdomain.com]',
  //supportPhone: '[+234 ...]',
  // Nigeria's data protection regulator, effective 2023 (replaces the
  // earlier NDPR). If you appoint a Data Protection Officer/Compliance
  // Officer (required once you cross the NDPA's processing-volume
  // thresholds), name them here instead of just the support email.
  dataProtectionContact: '[DPO NAME/EMAIL, OR "support email above" IF NOT YET REQUIRED]',
  //lastUpdated: 'TBD \u2014 set this to the date you actually publish these pages',
  governingLawState: '[STATE, NIGERIA]', // for the Terms' governing-law clause
};
