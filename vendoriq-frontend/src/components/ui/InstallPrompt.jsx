import { Download, X } from 'lucide-react'
import { useInstall } from '../../context/InstallContext'

export default function InstallPrompt() {
  const { canInstall, installed, bannerDismissed, dismissBanner, promptInstall } = useInstall()

  if (!canInstall || installed || bannerDismissed) return null

  return (
    <div className="fixed bottom-20 lg:bottom-4 left-4 right-4 z-50 animate-fade-in">
      <div className="card-accent p-4 flex items-center gap-3 shadow-xl shadow-black/40">
        <div className="w-8 h-8 bg-saffron-500/15 rounded-lg flex items-center justify-center flex-shrink-0">
          <Download size={16} className="text-saffron-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-text">Install VendorIQ</p>
          <p className="text-xs text-slate-dim">Add to your home screen for quick access</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={promptInstall} className="btn-primary text-xs px-3 py-2">Install</button>
          <button onClick={dismissBanner} aria-label="Dismiss" className="text-slate-dim hover:text-slate-muted">
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
