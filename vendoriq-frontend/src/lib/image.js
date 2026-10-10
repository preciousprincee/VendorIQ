/**
 * Shrink a photo in the browser BEFORE uploading it.
 *
 * Product photos are limited to one small picture per product (the server
 * refuses anything over 1 MB and re-encodes what it accepts). A phone camera
 * produces 3-8 MB originals, so rather than bounce people with "too large"
 * the app resizes and compresses first - the result is usually 60-250 KB,
 * which also makes uploads quick on a weak connection.
 */
export const MAX_ORIGINAL_BYTES = 25 * 1024 * 1024 // refuse absurd files outright; we only decode what we must
export const MAX_UPLOAD_BYTES = 1024 * 1024        // what the server accepts
const MAX_EDGE = 1024
const ATTEMPTS = [[MAX_EDGE, 0.82], [MAX_EDGE, 0.7], [800, 0.7], [640, 0.6]]

async function decode(file) {
  if (typeof createImageBitmap === 'function') {
    try { return await createImageBitmap(file) } catch { /* fall through to <img> */ }
  }
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode')) }
    img.src = url
  })
}

const toBlob = (canvas, quality) => new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))

/** Returns a small JPEG File, or throws an Error with a message fit to show the user. */
export async function prepareProductPhoto(file) {
  if (!file.type.startsWith('image/')) throw new Error('Please choose an image file.')
  if (file.size > MAX_ORIGINAL_BYTES) throw new Error('That picture is far too large. Please choose a smaller one.')
  let source
  try { source = await decode(file) } catch { throw new Error('Could not read that image. Try a JPEG or PNG photo.') }

  const { width, height } = source
  for (const [edge, quality] of ATTEMPTS) {
    const scale = Math.min(1, edge / Math.max(width, height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#ffffff'            // transparent PNGs would otherwise turn black as JPEG
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height)
    const blob = await toBlob(canvas, quality)
    if (blob && blob.size <= MAX_UPLOAD_BYTES) {
      source.close?.()
      return new File([blob], 'photo.jpg', { type: 'image/jpeg' })
    }
  }
  source.close?.()
  throw new Error('Could not make that photo small enough. Please try a different picture.')
}
