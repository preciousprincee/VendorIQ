import { useState } from 'react'
import { WifiOff, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useOffline } from '../../context/OfflineContext'
import SyncIssuesModal from './SyncIssuesModal'

/**
 * One line that always tells the cashier the truth about their data:
 * offline (and what is waiting), syncing, or something needing attention.
 * Renders nothing when everything is online and in sync.
 */
export default function OfflineBanner() {
  const { online, pending, failed, syncing, syncNow, persistent } = useOffline()
  const [showIssues, setShowIssues] = useState(false)

  if (online && pending === 0 && failed.length === 0 && persistent) return null

  let tone = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30'
  let icon = <WifiOff size={15} className="flex-shrink-0" />
  let text = ''

  if (failed.length > 0) {
    tone = 'bg-red-500/10 text-red-700 dark:text-red-300 border-red-500/30'
    icon = <AlertTriangle size={15} className="flex-shrink-0" />
    text = `${failed.length} offline ${failed.length === 1 ? 'item needs' : 'items need'} your attention`
  } else if (!online) {
    text = pending > 0
      ? `You're offline - ${pending} ${pending === 1 ? 'sale is' : 'sales are'} saved on this device and will sync automatically.`
      : "You're offline - you can keep selling. Sales are saved on this device and sync when you're back online."
  } else if (pending > 0) {
    icon = <RefreshCw size={15} className={`flex-shrink-0 ${syncing ? 'animate-spin' : ''}`} />
    tone = 'bg-brand-500/10 text-brand-700 dark:text-brand-300 border-brand-500/30'
    text = `Syncing ${pending} offline ${pending === 1 ? 'item' : 'items'}...`
  } else if (!persistent) {
    text = "This browser can't keep offline data after you close it. Stay online, or don't close the app with unsynced sales."
  } else {
    icon = <CheckCircle2 size={15} className="flex-shrink-0" />
  }

  return (
    <>
      <div role="status" className={`flex items-center gap-2 px-4 py-2 text-xs border-b ${tone}`}>
        {icon}
        <span className="flex-1 min-w-0">{text}</span>
        {failed.length > 0 && (
          <button onClick={() => setShowIssues(true)} className="font-semibold underline flex-shrink-0">Review</button>
        )}
        {failed.length === 0 && online && pending > 0 && !syncing && (
          <button onClick={syncNow} className="font-semibold underline flex-shrink-0">Sync now</button>
        )}
      </div>
      {showIssues && <SyncIssuesModal onClose={() => setShowIssues(false)} />}
    </>
  )
}
