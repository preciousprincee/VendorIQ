import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider, useAuth } from './context/AuthContext'
import { StoreProvider, useStore } from './context/StoreContext'
import { SubscriptionProvider } from './context/SubscriptionContext'
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
import SubscriptionPage from './pages/SubscriptionPage'

function RequireAuth({ children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/welcome" replace />
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
  return <Navigate to={activeStore?.role === 'CASHIER' ? '/sales' : '/dashboard'} replace />
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/welcome" element={<WelcomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/stores" element={<RequireAuth><StoresPage /></RequireAuth>} />
      <Route path="/" element={
        <RequireAuth><RequireStore><AppLayout /></RequireStore></RequireAuth>
      }>
        <Route index element={<DefaultRedirect />} />
        <Route path="dashboard" element={<RequireFinancialAccess><DashboardPage /></RequireFinancialAccess>} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="sales" element={<SalesPage />} />
        <Route path="invoices" element={<InvoicesPage />} />
        <Route path="staff" element={<RequireStaffAccess><StaffPage /></RequireStaffAccess>} />
        <Route path="insights" element={<RequireFinancialAccess><InsightsPage /></RequireFinancialAccess>} />
        <Route path="ai" element={<RequireFinancialAccess><AIPage /></RequireFinancialAccess>} />
        <Route path="expenses" element={<RequireFinancialAccess><ExpensesPage /></RequireFinancialAccess>} />
        <Route path="transactions" element={<RequireFinancialAccess><TransactionsPage /></RequireFinancialAccess>} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="subscription" element={<RequireOwnerOnly><SubscriptionPage /></RequireOwnerOnly>} />
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
            <AppRoutes />
            <InstallPrompt />
            <Toaster
              position="top-center"
              toastOptions={{
                style: { background: 'rgb(var(--c-navy-800))', color: 'rgb(var(--c-text))', border: '1px solid rgb(var(--c-navy-700))', fontSize: '14px' },
                success: { iconTheme: { primary: 'rgb(var(--c-brand-500))', secondary: 'rgb(var(--c-navy-800))' } },
                error: { iconTheme: { primary: '#EF4444', secondary: 'rgb(var(--c-navy-800))' } },
              }}
            />
          </SubscriptionProvider>
        </StoreProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
