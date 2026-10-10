import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from './context/AuthContext'
import { StoreProvider, useStore } from './context/StoreContext'
import { SubscriptionProvider, useSubscription } from './context/SubscriptionContext'
import { OfflineProvider } from './context/OfflineContext'
import AppLayout from './components/layout/AppLayout'
import InstallPrompt from './components/ui/InstallPrompt'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import WelcomePage from './pages/WelcomePage'
import StoresPage from './pages/StoresPage'
import DashboardPage from './pages/DashboardPage'
import ProductsPage from './pages/ProductsPage'
import SalesPage from './pages/SalesPage'
import InvoicesPage from './pages/InvoicesPage'
import StaffPage from './pages/StaffPage'
import InsightsPage from './pages/InsightsPage'
import AIPage from './pages/AIPage'
import ExpensesPage from './pages/ExpensesPage'
import TransactionsPage from './pages/TransactionsPage'
import ProfilePage from './pages/ProfilePage'
import SettingsPage from './pages/SettingsPage'
import ReferralsPage from './pages/ReferralsPage'
import SubscriptionPage from './pages/SubscriptionPage'
import VerifyPage from './pages/VerifyPage'
import CustomersPage from './pages/CustomersPage'
import ShiftsPage from './pages/ShiftsPage'
import PrivacyPolicyPage from './pages/legal/PrivacyPolicyPage'
import TermsPage from './pages/legal/TermsPage'
import CookiePolicyPage from './pages/legal/CookiePolicyPage'
import RefundPolicyPage from './pages/legal/RefundPolicyPage'
import CookieNotice from './components/legal/CookieNotice'
import { identify, pageview } from './lib/analytics'

// Feeds analytics from the app's own state. Renders nothing (see lib/analytics.js).
function AnalyticsBridge() {
  const { user } = useAuth()
  const { activeStore } = useStore()
  const { subscription, plan } = useSubscription()
  const location = useLocation()
  const userId = user?.id
  const role = activeStore?.role
  const planKnown = subscription ? plan : undefined   // don't claim 'FREE' before the plan has loaded

  // Identity: the opaque user id plus two low-cardinality facts.
  useEffect(() => {
    identify(userId ? { id: userId } : null, { role, plan: planKnown })
  }, [userId, role, planKnown])

  // One $pageview per route change. '/' only redirects to the real landing page, so it is not counted.
  useEffect(() => {
    if (location.pathname !== '/') pageview(location.pathname)
  }, [location.pathname])

  return null
}

function RequireAuth({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/welcome" replace />
  // Email AND phone must be verified before anything else (the trial's
  // anti-abuse key is the phone number, and the email is where receipts go).
  // `needs_verification` comes from the server - see AuthContext.refreshUser,
  // which re-syncs it on every app load so pre-existing accounts are caught too.
  if (user.needs_verification) return <Navigate to="/verify" replace />
  return children
}

function RequireStore({ children }) {
  const { activeStore } = useStore()
  if (!activeStore) return <Navigate to="/stores" replace />
  return children
}

// Dashboard, Insights, and AI Assistant show revenue/profit figures, so
// cashiers are redirected away from them - only owners and managers may view.
function RequireFinancialAccess({ children }) {
  const { activeStore } = useStore()
  if (activeStore?.role === 'CASHIER') return <Navigate to="/sales" replace />
  return children
}

// Staff management isn't financial, but cashiers still shouldn't see who
// else works at the store or what their roles/pay-grade-adjacent info is.
function RequireStaffAccess({ children }) {
  const { activeStore } = useStore()
  if (activeStore?.role === 'CASHIER') return <Navigate to="/sales" replace />
  return children
}

// Expenses/overhead and true net profit reveal the store's cost structure
// (rent, salaries) - reserved for the owner only, not managers.
function RequireOwnerOnly({ children }) {
  const { activeStore } = useStore()
  if (activeStore?.role !== 'OWNER') return <Navigate to={activeStore?.role === 'CASHIER' ? '/sales' : '/dashboard'} replace />
  return children
}

function DefaultRedirect() {
  const { activeStore } = useStore()
  // Offline, the dashboard has nothing to show (it is all live numbers) but the
  // till works - open on it so a shop that starts its day without internet can sell.
  const offline = typeof navigator !== 'undefined' && navigator.onLine === false
  return <Navigate to={activeStore?.role === 'CASHIER' || offline ? '/sales' : '/dashboard'} replace />
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/welcome" element={<WelcomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/legal/privacy" element={<PrivacyPolicyPage />} />
      <Route path="/legal/terms" element={<TermsPage />} />
      <Route path="/legal/cookies" element={<CookiePolicyPage />} />
      <Route path="/legal/refunds" element={<RefundPolicyPage />} />
      <Route path="/verify" element={<VerifyPage />} />
      <Route path="/stores" element={<RequireAuth><StoresPage /></RequireAuth>} />
      <Route path="/" element={
        <RequireAuth><AppLayout /></RequireAuth>
      }>
        <Route index element={<RequireStore><DefaultRedirect /></RequireStore>} />
        <Route path="dashboard" element={<RequireStore><RequireFinancialAccess><DashboardPage /></RequireFinancialAccess></RequireStore>} />
        <Route path="products" element={<RequireStore><ProductsPage /></RequireStore>} />
        <Route path="sales" element={<RequireStore><SalesPage /></RequireStore>} />
        <Route path="invoices" element={<RequireStore><InvoicesPage /></RequireStore>} />
        <Route path="customers" element={<RequireStore><CustomersPage /></RequireStore>} />
        <Route path="shifts" element={<RequireStore><ShiftsPage /></RequireStore>} />
        <Route path="staff" element={<RequireStore><RequireStaffAccess><StaffPage /></RequireStaffAccess></RequireStore>} />
        <Route path="insights" element={<RequireStore><RequireFinancialAccess><InsightsPage /></RequireFinancialAccess></RequireStore>} />
        <Route path="ai" element={<RequireStore><RequireFinancialAccess><AIPage /></RequireFinancialAccess></RequireStore>} />
        <Route path="expenses" element={<RequireStore><RequireFinancialAccess><ExpensesPage /></RequireFinancialAccess></RequireStore>} />
        <Route path="transactions" element={<RequireStore><RequireFinancialAccess><TransactionsPage /></RequireFinancialAccess></RequireStore>} />
        {/* Profile and Referrals are account-level, not store-level - a
            brand-new user with no store yet can still reach these (e.g.
            from a "Profile" link on /stores) to grab their referral code
            and link, or edit their name/phone, before ever creating one. */}
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="referrals" element={<ReferralsPage />} />
        <Route path="subscription" element={<RequireStore><RequireOwnerOnly><SubscriptionPage /></RequireOwnerOnly></RequireStore>} />
      </Route>
      <Route path="*" element={<RequireAuth><RequireStore><DefaultRedirect /></RequireStore></RequireAuth>} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <StoreProvider>
          <SubscriptionProvider>
            <OfflineProvider>
            <AnalyticsBridge />
            <AppRoutes />
            <InstallPrompt />
            <CookieNotice />
            <Toaster
              position="top-center"
              toastOptions={{
                style: { background: 'rgb(var(--c-navy-800))', color: 'rgb(var(--c-text))', border: '1px solid rgb(var(--c-navy-700))', fontSize: '14px' },
                success: { iconTheme: { primary: 'rgb(var(--c-brand-500))', secondary: 'rgb(var(--c-navy-800))' } },
                error: { iconTheme: { primary: '#EF4444', secondary: 'rgb(var(--c-navy-800))' } },
              }}
            />
            </OfflineProvider>
          </SubscriptionProvider>
        </StoreProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
