/**
 * Barcode matching shared by the till and the product list.
 *
 * A code read by the camera, typed by hand, or typed by a USB/Bluetooth scanner can differ from the stored
 * one in harmless ways: stray spaces, or leading zeros (a 12-digit UPC-A is the same product as its 13-digit
 * EAN-13 form "0" + UPC-A, and some scanners/apps drop or add that zero). Compare the normalised forms so
 * those all find the product - while codes that are really different never match.
 */
export function normalizeBarcode(code) {
  const text = String(code ?? '').trim()
  if (!text) return ''
  return /^\d+$/.test(text) ? (text.replace(/^0+/, '') || '0') : text
}

export function sameBarcode(a, b) {
  const x = normalizeBarcode(a)
  return x !== '' && x === normalizeBarcode(b)
}

/** All products whose barcode matches `code` (normally 0 or 1; more than one means the shop's data has a duplicate). */
export function productsForBarcode(products, code) {
  return products.filter((p) => sameBarcode(p.barcode, code))
}

/**
 * The camera decodes ~8 times a second, so a code that stays in view is reported again and again.
 * Wraps `report` so the same text is passed on once, and again only after `windowMs`. A different code is
 * always passed on immediately.
 */
export function dedupeScans(report, windowMs = 1500, now = Date.now) {
  let lastText = ''
  let lastAt = -Infinity
  return (text) => {
    const t = now()
    if (text === lastText && t - lastAt < windowMs) return
    lastText = text
    lastAt = t
    report(text)
  }
}
