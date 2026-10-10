import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Store, Plus, Package, Users, X, Trash2, User } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useAuth } from '../context/AuthContext'
import { useSubscription } from '../context/SubscriptionContext'
import UsageLimit from '../components/billing/UsageLimit'
import ConfirmDialog from '../components/ConfirmDialog'
import api from '../lib/api'
import { getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

export default function StoresPage() {
  const { selectStore, clearStore } = useStore()
  const { user } = useAuth()
  const { limits } = useSubscription()
  const navigate = useNavigate()
  const [stores, setStores] = useState({ owned: [], staff: [] })
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', location: '' })
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const fetchStores = async () => {
    try {
      const { data } = await api.get('/stores/')
      setStores(data)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchStores() }, [])

  const handleSelect = (store) => {
    sessionStorage.removeItem('viq_account_only')
    selectStore(store)
    navigate('/dashboard')
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    setCreating(true)
    try {
      const { data } = await api.post('/stores/', form)
      toast.success(`${data.store.name} created`)
      setShowForm(false)
      setForm({ name: '', location: '' })
      fetchStores()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = (e, store) => {
    e.stopPropagation()
    setPendingDelete(store)
  }

  const confirmDelete = async () => {
    const store = pendingDelete
    setDeleting(true)
    try {
      await api.delete(`/stores/${store.id}/`)
      toast.success(`${store.name} deleted`)
      fetchStores()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  const allStores = [
    ...stores.owned.map(s => ({ ...s, role: 'OWNER' })),
    ...stores.staff,
  ]

  return (
    <div className="min-h-screen bg-navy-900 px-4 py-10">
      <div className="max-w-lg mx-auto animate-fade-in">
        <div className="flex items-center justify-between gap-3 mb-8">
          <div className="flex items-center gap-3">
            {/* The real VendorIQ logo, same as the login screens and the in-store header
                (this used to be a generic bar-chart placeholder). */}
            <div className="w-9 h-9 rounded-xl overflow-hidden flex items-center justify-center flex-shrink-0">
              <img src="/icons/logo.png" alt="VendorIQ" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-text">VendorIQ</h1>
              <p className="text-xs text-slate-dim">Pick a store to continue</p>
            </div>
          </div>
          <button
            onClick={() => {
              // Profile/settings/referrals opened from here show without the
              // in-store menu and tabs (see AppLayout's account-only mode).
              sessionStorage.setItem('viq_account_only', '1')
              navigate('/profile')
            }}
            aria-label="Profile"
            className="w-10 h-10 rounded-full bg-brand-50 dark:bg-brand-500/15 border border-brand-500/30 flex items-center justify-center flex-shrink-0 text-brand-600 dark:text-brand-400 hover:bg-brand-100 dark:hover:bg-brand-500/25 transition-colors"
          >
            <User size={18} />
          </button>
        </div>

        <p className="text-sm text-slate-muted mb-4">
          Hi {user?.name?.split(' ')[0]}, select a store or create a new one.
        </p>

        {limits?.maxStores != null && (
          <div className="mb-4">
            <UsageLimit label="Stores" used={stores.owned.length} limit={limits.maxStores} />
          </div>
        )}

        {loading ? (
          <div className="space-y-3">
            {[1, 2].map(i => <div key={i} className="card p-4 animate-pulse h-16" />)}
          </div>
        ) : (
          <div className="space-y-3 mb-6">
            {allStores.length === 0 ? (
              <div className="card p-8 text-center">
                <Store size={32} className="text-slate-dim mx-auto mb-3" />
                <p className="text-slate-muted text-sm">No stores yet. Create your first one.</p>
              </div>
            ) : (
              allStores.map(store => (
                <div key={store.id} role="button" tabIndex={0} onClick={() => handleSelect(store)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(store) } }}
                  className="card w-full p-4 text-left hover:border-brand-500/50 hover:bg-navy-700/50 transition-all group cursor-pointer">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-semibold text-slate-text group-hover:text-brand-500 transition-colors">{store.name}</h3>
                        <span className={`badge ${store.role === 'OWNER' ? 'badge-warning' : 'badge-success'}`}>{store.role}</span>
                      </div>
                      {store.location && <p className="text-xs text-slate-dim">{store.location}</p>}
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex gap-3 text-xs text-slate-dim">
                        <span className="flex items-center gap-1"><Package size={12} />{store.products_count ?? 0}</span>
                        <span className="flex items-center gap-1"><Users size={12} />{store.staff_count ?? 0}</span>
                      </div>
                      {store.role === 'OWNER' && (
                        <button
                          onClick={(e) => handleDelete(e, store)}
                          className="p-1.5 -m-1.5 text-slate-dim hover:text-red-500 dark:hover:text-red-400 transition-colors flex-shrink-0"
                          title="Delete store"
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {showForm ? (
          <div className="card p-5 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-text">New store</h3>
              <button onClick={() => setShowForm(false)} aria-label="Close" className="text-slate-dim hover:text-slate-muted"><X size={18} /></button>
            </div>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label htmlFor="store-name" className="label">Store name</label>
                <input id="store-name" className="input" placeholder="e.g. Mama Ngozi Store" value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
              </div>
              <div>
                <label htmlFor="store-location" className="label">Location <span className="text-slate-dim normal-case">(optional)</span></label>
                <input id="store-location" className="input" placeholder="e.g. Onitsha Main Market" value={form.location}
                  onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
              </div>
              <button type="submit" disabled={creating} className="btn-primary w-full">
                {creating ? 'Creating...' : 'Create store'}
              </button>
            </form>
          </div>
        ) : (
          <button onClick={() => setShowForm(true)}
            className="w-full card p-4 border-dashed hover:border-brand-500/50 transition-colors flex items-center justify-center gap-2 text-slate-muted hover:text-slate-text">
            <Plus size={18} />
            <span className="text-sm font-medium">Add a new store</span>
          </button>
        )}
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        title={`Delete "${pendingDelete?.name}"?`}
        message="This will permanently remove all its products, sales, invoices, and staff. This cannot be undone."
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}
