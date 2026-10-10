import { useEffect, useRef, useState } from 'react'

/**
 * Live camera barcode scanner.
 *
 * Why this is one shared component (it used to be three copies of the same
 * code in ProductsPage/SalesPage, all with the same two bugs):
 *
 *  1. "Blank screen after allowing the camera". The old code set
 *     scanning=true and, in the SAME tick, passed videoRef.current to the
 *     reader - but the <video> is only rendered on the NEXT render, so the
 *     ref was still null. zxing then quietly created its own detached video
 *     element: the camera light came on, the permission prompt passed, and
 *     the visible <video> stayed black. Here the <video> is already mounted
 *     when the effect runs, so the ref is always real.
 *  2. `reader.reset()` does not exist in @zxing/browser 0.1.x (start now
 *     returns a controls object with .stop()), so "stop" threw and the
 *     camera was never released. Cleanup below stops the controls AND every
 *     track on the stream, so the camera light always goes off.
 *
 * Mounting this component starts the camera; unmounting stops it.
 */
export default function BarcodeScanner({ onDetected, onError, className = '' }) {
  const videoRef = useRef(null)
  const [status, setStatus] = useState('starting') // starting | scanning | error
  const [message, setMessage] = useState('')

  // Keep the latest callbacks without restarting the camera when a parent re-renders.
  const detectedRef = useRef(onDetected)
  const errorRef = useRef(onError)
  useEffect(() => { detectedRef.current = onDetected; errorRef.current = onError })

  useEffect(() => {
    let cancelled = false
    let controls = null
    const video = videoRef.current

    const fail = (text) => {
      if (cancelled) return
      setStatus('error')
      setMessage(text)
      errorRef.current?.(text)
    }

    const describe = (err) => {
      switch (err?.name) {
        case 'NotAllowedError':
        case 'SecurityError':
          return 'Camera access was blocked. Allow the camera for this site in your browser settings, then try again.'
        case 'NotFoundError':
        case 'DevicesNotFoundError':
          return 'No camera was found on this device.'
        case 'NotReadableError':
        case 'TrackStartError':
          return 'The camera is being used by another app or tab. Close it and try again.'
        default:
          return 'Could not start the camera.'
      }
    }

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        fail(window.isSecureContext
          ? 'This browser does not support camera scanning.'
          : 'Camera scanning needs a secure (https) connection.')
        return
      }
      try {
        const [{ BrowserMultiFormatReader }, { DecodeHintType, BarcodeFormat }] = await Promise.all([
          import('@zxing/browser'),
          import('@zxing/library'),
        ])
        if (cancelled) return

        // Only the formats that appear on products (plus QR) - decoding is
        // faster and far less likely to misread than "try everything".
        const hints = new Map()
        hints.set(DecodeHintType.POSSIBLE_FORMATS, [
          BarcodeFormat.EAN_13, BarcodeFormat.EAN_8, BarcodeFormat.UPC_A, BarcodeFormat.UPC_E,
          BarcodeFormat.CODE_128, BarcodeFormat.CODE_39, BarcodeFormat.ITF, BarcodeFormat.QR_CODE,
        ])
        hints.set(DecodeHintType.TRY_HARDER, true)
        const reader = new BrowserMultiFormatReader(hints, { delayBetweenScanAttempts: 120 })

        const onResult = (result) => {
          if (result && !cancelled) detectedRef.current?.(result.getText())
        }

        try {
          // Prefer the back camera on phones; laptops just use their webcam.
          controls = await reader.decodeFromConstraints(
            { video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } } },
            video,
            onResult,
          )
        } catch (err) {
          if (err?.name === 'OverconstrainedError' || err?.name === 'ConstraintNotSatisfiedError') {
            controls = await reader.decodeFromVideoDevice(undefined, video, onResult)
          } else {
            throw err
          }
        }
        if (cancelled) { controls?.stop?.(); return }
        setStatus('scanning')
      } catch (err) {
        console.error('Barcode scanner failed to start', err)
        fail(describe(err))
      }
    }

    start()

    return () => {
      cancelled = true
      try { controls?.stop?.() } catch { /* already stopped */ }
      // Belt and braces: release the camera even if the controls object is missing.
      const stream = video?.srcObject
      if (stream && typeof stream.getTracks === 'function') stream.getTracks().forEach((t) => t.stop())
      if (video) video.srcObject = null
    }
  }, [])

  return (
    <div className={`relative rounded-xl overflow-hidden bg-black aspect-video ${className}`}>
      {/* muted + playsInline are REQUIRED for the stream to autoplay (Chrome/Safari/iOS). */}
      <video ref={videoRef} className="w-full h-full object-cover" muted playsInline autoPlay />
      {status === 'scanning' && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-48 h-24 border-2 border-brand-500 rounded opacity-70" />
        </div>
      )}
      {status === 'starting' && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-white/80">Starting camera...</div>
      )}
      {status === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-white/90">{message}</div>
      )}
    </div>
  )
}
