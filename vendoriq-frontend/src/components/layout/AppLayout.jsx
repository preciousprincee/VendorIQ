import { useState, useEffect, useRef } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Package, ShoppingCart, FileText, Users, TrendingUp, BarChart3, Bot, Store, LogOut, Menu, ChevronDown, ChevronRight, Wallet, Bell, AlertTriangle, PackageX, Clock, User, Sun, Moon, X } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { useStore } from '../../context/StoreContext'
import { useTheme } from '../../context/ThemeContext'
import api from '../../lib/api'
import { formatDate } from '../../lib/utils'

const NOTIF_ICONS = { out_of_stock: PackageX, low_stock: AlertTriangle, stale_invoice: Clock }
const SEVERITY_COLOR = { high: 'text-red-500 dark:text-red-400', medium: 'text-amber-500 dark:text-amber-400', low: 'text-slate-dim' }

function NotificationBell() {
  const { activeStore } = useStore()
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState([])
  const [open, setOpen] = useState(false)
  const panelRef = useRef(null)
  const canSee = activeStore && activeStore.role !== 'CASHIER'

  useEffect(() => {
    if (!canSee) { setNotifications([]); return }
    const fetchNotifications = () => {
      api.get(`/stores/${activeStore.id}/insights/notifications/`)
        .then(({ data }) => setNotifications(data.notifications))
        .catch(() => {}) // non-critical - fail silently rather than toast-spamming the whole app
    }
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 2 * 60 * 1000)
    return () => clearInterval(interval)
  }, [activeStore, canSee])

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  if (!canSee) return <div className="w-8 h-8" />

  return (
    <div className="relative" ref={panelRef}>
      <button onClick={() => setOpen(o => !o)} className="relative text-slate-muted hover:text-slate-text p-1.5 transition-colors" title="Notifications">
        <Bell size={19} />
        {notifications.length > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
            {notifications.length > 9 ? '9+' : notifications.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-w-[90vw] card z-40 max-h-96 overflow-y-auto">
          <div className="px-4 py-3 border-b border-navy-700">
            <p className="text-sm font-semibold text-slate-text">Notifications</p>
          </div>
          {notifications.length === 0 ? (
            <p className="px-4 py-6 text-center text-xs text-slate-dim">Nothing needs your attention right now.</p>
          ) : (
            <div className="divide-y divide-navy-700">
              {notifications.map(n => {
                const Icon = NOTIF_ICONS[n.type] || Bell
                return (
                  <button key={n.id} onClick={() => { setOpen(false); navigate(n.link) }}
                    className="w-full text-left px-4 py-3 hover:bg-navy-700/50 transition-colors flex gap-3">
                    <Icon size={16} className={`flex-shrink-0 mt-0.5 ${SEVERITY_COLOR[n.severity] || 'text-slate-dim'}`} />
                    <div className="min-w-0">
                      <p className="text-xs text-slate-text">{n.message}</p>
                      <p className="text-[11px] text-slate-dim mt-0.5">{formatDate(n.createdAt)}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ThemeToggle({ expanded = false }) {
  const { theme, toggleTheme } = useTheme()
  if (expanded) {
    return (
      <button onClick={toggleTheme} className="nav-item w-full justify-between">
        <span className="flex items-center gap-3">
          {theme === 'dark' ? <Moon size={17} /> : <Sun size={17} />}
          {theme === 'dark' ? 'Dark mode' : 'Light mode'}
        </span>
        <span className={`w-9 h-5 rounded-full flex items-center px-0.5 transition-colors ${theme === 'dark' ? 'bg-brand-500 justify-end' : 'bg-navy-600 justify-start'}`}>
          <span className="w-4 h-4 rounded-full bg-white shadow-sm" />
        </span>
      </button>
    )
  }
  return (
    <button onClick={toggleTheme} className="text-slate-muted hover:text-slate-text p-1.5 transition-colors" title="Toggle theme">
      {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
    </button>
  )
}

// financialOnly items show revenue, profit, or cost figures and are hidden from cashiers.
// cashierHidden items aren't financial but still aren't meant for cashiers (e.g. staff management).
// "primary" items live in the bottom tab bar on mobile; everything else lives behind "More".
const PRIMARY_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Home', financialOnly: true },
  { to: '/products', icon: Package, label: 'Products' },
  { to: '/sales', icon: ShoppingCart, label: 'Sales' },
  { to: '/invoices', icon: FileText, label: 'Invoices' },
]
const SECONDARY_ITEMS = [
  { to: '/staff', icon: Users, label: 'Staff', cashierHidden: true },
  { to: '/insights', icon: TrendingUp, label: 'Insights', financialOnly: true },
  { to: '/expenses', icon: Wallet, label: 'Expenses', financialOnly: true },
  { to: '/ai', icon: Bot, label: 'AI Assistant', financialOnly: true },
]

export default function AppLayout() {
  const { user, logout } = useAuth()
  const { activeStore, clearStore } = useStore()
  const navigate = useNavigate()
  const [drawerOpen, setDrawerOpen] = useState(false)

  const handleLogout = () => { clearStore(); logout(); navigate('/login') }
  const handleSwitchStore = () => { clearStore(); navigate('/stores') }
  const isCashier = activeStore?.role === 'CASHIER'
  const visible = (items) => items.filter(item => (!item.financialOnly && !item.cashierHidden) || !isCashier)
  const primaryItems = visible(PRIMARY_ITEMS)
  const secondaryItems = visible(SECONDARY_ITEMS)
  const allNavItems = [...primaryItems, ...secondaryItems]

  return (
    <div className="flex h-screen overflow-hidden">
      {drawerOpen && (
        <div className="fixed inset-0 bg-black/50 z-20 lg:hidden" onClick={() => setDrawerOpen(false)} />
      )}

      {/* Desktop sidebar - full nav, always visible at lg+. Also doubles as the
          mobile slide-out drawer (opened via hamburger or the "More" tab). */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-30 w-64 bg-navy-900 flex flex-col border-r border-navy-700 transition-transform duration-200 ${drawerOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="px-4 py-5 border-b border-navy-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-brand-500 rounded-lg flex items-center justify-center">
              <BarChart3 size={15} className="text-white" />
            </div>
            <span className="font-bold text-slate-text tracking-tight">VendorIQ</span>
          </div>
          <button onClick={() => setDrawerOpen(false)} className="text-slate-muted hover:text-slate-text lg:hidden">
            <X size={20} />
          </button>
        </div>

        {activeStore && (
          <button onClick={handleSwitchStore} className="mx-3 mt-3 p-3 bg-navy-950 rounded-xl border border-navy-700 text-left hover:border-brand-500/50 transition-colors group">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Store size={14} className="text-brand-500" />
                <span className="text-xs text-slate-muted font-medium uppercase tracking-wider">Active store</span>
              </div>
              <ChevronDown size={12} className="text-slate-dim" />
            </div>
            <p className="text-sm font-semibold text-slate-text mt-1 truncate">{activeStore.name}</p>
          </button>
        )}

        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          {allNavItems.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} onClick={() => setDrawerOpen(false)}
              className={({ isActive }) => isActive ? 'nav-item-active' : 'nav-item'}>
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-navy-700 space-y-1">
          <ThemeToggle expanded />
          <NavLink
            to="/profile"
            className={({ isActive }) => `flex items-center gap-3 px-3 py-2 mt-1 mb-1 rounded-xl transition-colors ${isActive ? 'bg-navy-700/70' : 'hover:bg-navy-700/50'}`}
          >
            <div className="w-7 h-7 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0">
              <span className="text-xs font-bold text-brand-500">{user?.name?.[0]?.toUpperCase()}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-text truncate">{user?.name}</p>
              <p className="text-xs text-slate-dim truncate">{user?.email}</p>
            </div>
            <ChevronRight size={14} className="text-slate-dim flex-shrink-0" />
          </NavLink>
          <button onClick={handleLogout} className="nav-item w-full text-red-500 dark:text-red-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20">
            <LogOut size={17} />Sign out
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="flex items-center justify-between px-4 py-3 bg-navy-900 border-b border-navy-700 flex-shrink-0">
          <div className="flex items-center gap-2 lg:hidden">
            <button onClick={() => setDrawerOpen(true)} className="text-slate-muted hover:text-slate-text">
              <Menu size={22} />
            </button>
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-brand-500 rounded flex items-center justify-center">
                <BarChart3 size={13} className="text-white" />
              </div>
              <span className="font-bold text-slate-text text-sm">VendorIQ</span>
            </div>
          </div>
          <div className="hidden lg:block" />
          <div className="flex items-center gap-1">
            <div className="lg:hidden"><ThemeToggle /></div>
            <NotificationBell />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto pb-16 lg:pb-0"><Outlet /></main>

        {/* Bottom tab bar - mobile only. Desktop uses the full sidebar instead. */}
        <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-20 bg-navy-900 border-t border-navy-700 flex items-stretch">
          {primaryItems.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-medium transition-colors ${isActive ? 'text-brand-500' : 'text-slate-dim'}`}>
              <Icon size={20} />
              {label}
            </NavLink>
          ))}
          <NavLink to="/profile"
            className={({ isActive }) => `flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[11px] font-medium transition-colors ${isActive ? 'text-brand-500' : 'text-slate-dim'}`}>
            <User size={20} />
            Profile
          </NavLink>
        </nav>
      </div>
    </div>
  )
}
