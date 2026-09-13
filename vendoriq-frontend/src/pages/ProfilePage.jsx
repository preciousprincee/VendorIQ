import { useNavigate } from 'react-router-dom'
import { Mail, Phone, Store, LogOut, Sun, Moon, ChevronRight, Shield, BarChart2, ShoppingCart, Crown } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useStore } from '../context/StoreContext'
import { useTheme } from '../context/ThemeContext'
import { useSubscription } from '../context/SubscriptionContext'

const ROLE_META = {
  OWNER: { label: 'Owner', icon: Shield },
  MANAGER: { label: 'Manager', icon: BarChart2 },
  CASHIER: { label: 'Cashier', icon: ShoppingCart },
}

export default function ProfilePage() {
  const { user, logout } = useAuth()
  const { activeStore, clearStore } = useStore()
  const { theme, toggleTheme } = useTheme()
  const { isPro, isTrialActive, trialDaysRemaining } = useSubscription()
  const navigate = useNavigate()

  const handleLogout = () => { clearStore(); logout(); navigate('/login') }
  const handleSwitchStore = () => { clearStore(); navigate('/stores') }
  const roleMeta = activeStore ? (ROLE_META[activeStore.role] || ROLE_META.CASHIER) : null

  return (
    <div className="p-5 lg:p-6 max-w-lg lg:mx-auto animate-fade-in">
      <h1 className="text-xl font-bold text-slate-text mb-5">Profile</h1>

      <div className="card p-5 flex items-center gap-4 mb-5">
        <div className="w-14 h-14 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0">
          <span className="text-xl font-bold text-brand-600 dark:text-brand-400">{user?.name?.[0]?.toUpperCase()}</span>
        </div>
        <div className="min-w-0">
          <p className="text-base font-semibold text-slate-text truncate">{user?.name}</p>
          <p className="text-xs text-slate-dim truncate">{user?.email}</p>
        </div>
      </div>

      <div className="card divide-y divide-navy-700 mb-5">
        <div className="px-4 py-3 flex items-center gap-3">
          <Mail size={16} className="text-slate-dim flex-shrink-0" />
          <div className="min-w-0">
            <p className="label mb-0.5">Email</p>
            <p className="text-sm text-slate-text truncate">{user?.email}</p>
          </div>
        </div>
        {user?.phone && (
          <div className="px-4 py-3 flex items-center gap-3">
            <Phone size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0">
              <p className="label mb-0.5">Phone</p>
              <p className="text-sm text-slate-text truncate">{user.phone}</p>
            </div>
          </div>
        )}
        {activeStore && (
          <button onClick={handleSwitchStore} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
            <Store size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="label mb-0.5">Active store</p>
              <p className="text-sm text-slate-text truncate">
                {activeStore.name}
                {roleMeta && <span className="text-slate-dim"> · {roleMeta.label}</span>}
              </p>
            </div>
            <ChevronRight size={16} className="text-slate-dim flex-shrink-0" />
          </button>
        )}
      </div>

      {activeStore?.role === 'OWNER' && (
        <div className="card mb-5">
          <button onClick={() => navigate('/subscription')} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-navy-700/50 transition-colors text-left">
            <Crown size={16} className="text-slate-dim flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="label mb-0.5">Subscription &amp; billing</p>
              <p className="text-sm text-slate-text truncate">
                {isTrialActive
                  ? `Trial · ${trialDaysRemaining} day${trialDaysRemaining === 1 ? '' : 's'} left`
                  : isPro ? 'Pro plan' : 'Free plan'}
                {!isPro && <span className="text-brand-500 font-medium"> · Upgrade</span>}
              </p>
            </div>
            <ChevronRight size={16} className="text-slate-dim flex-shrink-0" />
          </button>
        </div>
      )}

      <div className="card mb-5">
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

      <button onClick={handleLogout} className="btn-ghost w-full flex items-center justify-center gap-2 text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20">
        <LogOut size={16} />Sign out
      </button>
    </div>
  )
}
