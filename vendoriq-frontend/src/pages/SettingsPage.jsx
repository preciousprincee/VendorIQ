import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, Sun, Moon, LogOut, Lock, Shield, FileText, RotateCcw, X, Download, CheckCircle2, RefreshCw, DatabaseBackup } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useStore } from '../context/StoreContext'
import { useTheme } from '../context/ThemeContext'
import { useInstall } from '../context/InstallContext'
import { useOffline } from '../context/OfflineContext'
import { setAccessToken, invalidatePendingRefresh } from '../lib/session'
import { useFeatureAccess } from '../hooks/useFeatureAccess'
import api from '../lib/api'
import { getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

function ChangePasswordForm({ onClose }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match.')
      return
    }
    setSaving(true)
    try {
      const { data } = await api.post('/auth/change-password/', { current_password: currentPassword, new_password: newPassword })
      // Changing the password invalidates every older token (including the
      // one this session was using) - the server hands back a fresh one so
      // the person isn't logged out the moment they save.
      // The server also replaced the HttpOnly session cookie; only the short-lived access token is ours to keep (in memory).
      if (data?.token) { invalidatePendingRefresh(); setAccessToken(data.token) }
      toast.success('Password changed.')
      onClose()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="card p-5 mb-5 space-y-3">
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm font-semibold text-slate-text">Change password</p>
        <button type="button" onClick={onClose} aria-label="Cancel" className="text-slate-muted hover:text-slate-text p-1">
          <X size={18} />
        </button>
      </div>
      <div>
        <label className="label mb-1 block">Current password</label>
        <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} className="input w-full" required />
      </div>
      <div>
        <label className="label mb-1 block">New password</label>
        <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="input w-full" minLength={8} required />
      </div>
      <div>
        <label className="label mb-1 block">Confirm new password</label>
        <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="input w-full" minLength={8} required />
      </div>
      <div className="flex gap-2 pt-1">
        <button type="button" onClick={onClose} className="btn-ghost flex-1">Cancel</button>
        <button type="submit" disabled={saving} className="btn-primary flex-1">{saving ? 'Saving\u2026' : 'Save password'}</button>
      </div>
    </form>
  )
}

export default function SettingsPage() {
  const { user, logout } = useAuth()
  const { activeStore, clearStore } = useStore()
  const { online, pending, failed, syncing, syncNow, confirmLogout } = useOffline()
  const { requireAccess: requireBackupAccess } = useFeatureAccess('cloud_backup')
  const [backingUp, setBackingUp] = useState(false)
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [changingPassword, setChangingPassword] = useState(false)
  const { canInstall, installed, isIOS, promptInstall } = useInstall()
  const [showInstallHelp, setShowInstallHelp] = useState(false)

  const handleInstall = async () => {
    if (canInstall) {
      const outcome = await promptInstall()
      if (outcome === 'accepted') toast.success('VendorIQ installed')
    } else {
      // The browser hasn't offered an install prompt (iOS Safari never does;
      // desktop Firefox/Safari don't support it) - tell them how to do it by hand.
      setShowInstallHelp(true)
    }
  }

  const handleLogout = () => { if (!confirmLogout()) return; clearStore(); logout(); navigate('/login') }

  const handleBackup = async () => {
    if (!requireBackupAccess()) return
    setBackingUp(true)
    try {
      const res = await api.get(`/stores/${activeStore.id}/backup/`, { responseType: 'blob', timeout: 90000 })
      const match = /filename="([^"]+)"/.exec(res.headers['content-disposition'] || '')
      const url = URL.createObjectURL(res.data)
      const link = document.createElement('a')
      link.href = url
      link.download = match ? match[1] : 'vendoriq-backup.json'
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
      toast.success('Backup downloaded - keep the file somewhere safe')
    } catch (err) {
      // With responseType 'blob' an error body is a Blob too - read the message out of it.
      let message = getErrorMessage(err)
      if (err.response?.data instanceof Blob) {
        try { message = JSON.parse(await err.response.data.text()).error || message } catch { /* keep the generic message */ }
      }
      toast.error(message)
    } finally {
      setBackingUp(false)
    }
  }

  return (
    <div className="p-5 lg:p-6 max-w-lg lg:mx-auto animate-fade-in">
      <div className="flex items-center gap-2 mb-5">
        <button onClick={() => navigate('/profile')} className="text-slate-muted hover:text-slate-text">
          <ChevronLeft size={22} />
        </button>
        <h1 className="text-xl font-bold text-slate-text">Settings</h1>
      </div>

      <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">Appearance</p>
      <div className="card mb-6">
        <button onClick={toggleTheme} className="w-full px-4 py-3 flex items-center justify-between hover:bg-navy-700/50 transition-colors">
          <span className="flex items-center gap-3 text-sm text-slate-text">
            {theme === 'dark' ? <Moon size={16} className="text-slate-dim" /> : <Sun size={16} className="text-slate-dim" />}
            {theme === 'dark' ? 'Dark mode' : 'Light mode'}
          </span>
          <span className={`w-9 h-5 rounded-full flex items-center px-0.5 transition-colors ${theme === 'dark' ? 'bg-brand-500 justify-end' : 'bg-navy-600 justify-start'}`}>
            <span className="w-4 h-4 rounded-full bg-white shadow-sm" />
          </span>
        </button>
      </div>

      <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">App</p>
      <div className="card mb-6">
        {installed ? (
          <div className="px-4 py-3 flex items-center gap-3">
            <CheckCircle2 size={16} className="text-green-500 flex-shrink-0" />
            <p className="text-sm text-slate-dim flex-1">VendorIQ is installed on this device.</p>
          </div>
        ) : (
          <>
            <button onClick={handleInstall} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
              <Download size={16} className="text-slate-dim flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-text">Install app</p>
                <p className="text-xs text-slate-dim">Add VendorIQ to your home screen or desktop</p>
              </div>
            </button>
            {showInstallHelp && (
              <p className="px-4 pb-3 text-xs text-slate-muted">
                {isIOS
                  ? 'On iPhone/iPad: tap the Share button in Safari, then "Add to Home Screen".'
                  : 'Open your browser menu and choose "Install app" or "Add to Home screen". If you don\'t see it, open VendorIQ in Chrome or Edge.'}
              </p>
            )}
          </>
        )}
      </div>

      <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">Offline &amp; data</p>
      <div className="card mb-6 divide-y divide-navy-700">
        <div className="px-4 py-3 flex items-center gap-3">
          <RefreshCw size={16} className={`text-slate-dim flex-shrink-0 ${syncing ? 'animate-spin' : ''}`} />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-text">
              {failed.length > 0 ? `${failed.length} item${failed.length === 1 ? '' : 's'} need attention`
                : pending > 0 ? `${pending} sale${pending === 1 ? '' : 's'} waiting to sync`
                : 'Everything is synced'}
            </p>
            <p className="text-xs text-slate-dim">{online ? 'Online - sales sync automatically.' : "Offline - you can keep selling; sales sync when you're back online."}</p>
          </div>
          {pending > 0 && online && <button onClick={syncNow} disabled={syncing} className="btn-ghost text-xs">Sync now</button>}
        </div>
        {activeStore?.role === 'OWNER' && (
          <button onClick={handleBackup} disabled={backingUp} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left disabled:opacity-60">
            <DatabaseBackup size={16} className="text-slate-dim flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-text">{backingUp ? 'Preparing your backup...' : 'Download a full backup'}</p>
              <p className="text-xs text-slate-dim">Products, sales, customers, expenses and invoices for {activeStore.name}</p>
            </div>
            <span className="badge bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400 flex-shrink-0">Pro</span>
          </button>
        )}
      </div>

      <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">Account</p>
      {changingPassword ? (
        <ChangePasswordForm onClose={() => setChangingPassword(false)} />
      ) : (
        <div className="card mb-6">
          {user?.has_password ? (
            <button onClick={() => setChangingPassword(true)} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
              <Lock size={16} className="text-slate-dim flex-shrink-0" />
              <p className="text-sm text-slate-text flex-1">Change password</p>
            </button>
          ) : (
            <div className="px-4 py-3 flex items-center gap-3">
              <Lock size={16} className="text-slate-dim flex-shrink-0" />
              <p className="text-sm text-slate-dim flex-1">You sign in with Google - no password to change.</p>
            </div>
          )}
        </div>
      )}

      <p className="text-xs font-semibold text-slate-dim uppercase tracking-widest mb-3">Legal</p>
      <div className="card divide-y divide-navy-700 mb-6">
        <button onClick={() => navigate('/legal/privacy', { state: { from: '/settings' } })} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
          <Shield size={16} className="text-slate-dim flex-shrink-0" />
          <p className="text-sm text-slate-text flex-1">Privacy Policy</p>
        </button>
        <button onClick={() => navigate('/legal/terms', { state: { from: '/settings' } })} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
          <FileText size={16} className="text-slate-dim flex-shrink-0" />
          <p className="text-sm text-slate-text flex-1">Terms &amp; Conditions</p>
        </button>
        <button onClick={() => navigate('/legal/refunds', { state: { from: '/settings' } })} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
          <RotateCcw size={16} className="text-slate-dim flex-shrink-0" />
          <p className="text-sm text-slate-text flex-1">Refund Policy</p>
        </button>
      </div>

      <button onClick={handleLogout} className="btn-ghost w-full flex items-center justify-center gap-2 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">
        <LogOut size={16} />Sign out
      </button>
    </div>
  )
}
