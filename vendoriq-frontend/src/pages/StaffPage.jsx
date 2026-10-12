import { useState, useEffect, useRef } from 'react'
import { Users, Plus, Trash2, Edit2, X, Shield, ShoppingCart, BarChart2 } from 'lucide-react'
import { useStore } from '../context/StoreContext'
import { useAuth } from '../context/AuthContext'
import { useSubscription } from '../context/SubscriptionContext'
import UsageLimit from '../components/billing/UsageLimit'
import ConfirmDialog from '../components/ConfirmDialog'
import api from '../lib/api'
import { formatDate, getErrorMessage } from '../lib/utils'
import toast from 'react-hot-toast'

const ROLE_META = {
  OWNER: { label: 'Owner', color: 'badge-warning', icon: Shield },
  MANAGER: { label: 'Manager', color: 'badge-success', icon: BarChart2 },
  CASHIER: { label: 'Cashier', color: 'badge-danger', icon: ShoppingCart },
}

export default function StaffPage() {
  const { activeStore } = useStore()
  const { user } = useAuth()
  const { limits } = useSubscription()
  const [staff, setStaff] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editRole, setEditRole] = useState('')
  const [form, setForm] = useState({ email: '', role: 'CASHIER' })
  const [pendingRemove, setPendingRemove] = useState(null)
  const [removing, setRemoving] = useState(false)
  const fetchStaffRef = useRef(0)

  const fetchStaff = async () => {
    // Same request-counter guard as ProductsPage/SalesPage/InvoicesPage.
    const requestId = ++fetchStaffRef.current
    try {
      const { data } = await api.get(`/stores/${activeStore.id}/staff/`)
      if (requestId !== fetchStaffRef.current) return
      setStaff(data.staff)
    } catch (err) {
      if (requestId === fetchStaffRef.current) toast.error(getErrorMessage(err))
    } finally {
      if (requestId === fetchStaffRef.current) setLoading(false)
    }
  }

  useEffect(() => { if (activeStore) fetchStaff() }, [activeStore])

  const handleAdd = async (e) => {
    e.preventDefault()
    if (user?.email && form.email.trim().toLowerCase() === user.email.toLowerCase()) {
      toast.error("You're already the owner - you can't add yourself as staff.")
      return
    }
    setSaving(true)
    try {
      await api.post(`/stores/${activeStore.id}/staff/`, form)
      toast.success('Staff member added')
      setShowForm(false)
      setForm({ email: '', role: 'CASHIER' })
      fetchStaff()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleUpdateRole = async (staffId) => {
    setSaving(true)
    try {
      await api.patch(`/stores/${activeStore.id}/staff/${staffId}/`, { role: editRole })
      toast.success('Role updated')
      setEditingId(null)
      fetchStaff()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = (member) => {
    setPendingRemove(member)
  }

  const confirmRemove = async () => {
    const member = pendingRemove
    setRemoving(true)
    try {
      await api.delete(`/stores/${activeStore.id}/staff/${member.id}/`)
      toast.success('Staff member removed')
      fetchStaff()
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setRemoving(false)
      setPendingRemove(null)
    }
  }

  return (
    <div className="p-5 lg:p-6 animate-fade-in">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-bold text-slate-text">Staff</h1>
        <button onClick={() => setShowForm(v => !v)} className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center hover:bg-brand-600 transition-colors flex-shrink-0">
          {showForm ? <X size={18} /> : <Plus size={18} />}
        </button>
      </div>

      {limits?.maxUsersPerStore != null && (
        <div className="mb-5">
          <UsageLimit label="Users" used={staff.length + 1} limit={limits.maxUsersPerStore} />
        </div>
      )}

      <div className="flex gap-4 mb-5 flex-wrap">
        {Object.entries(ROLE_META).map(([role, meta]) => (
          <div key={role} className="flex items-center gap-1.5 text-xs text-slate-muted">
            <meta.icon size={12} />
            <span className="font-medium">{meta.label}</span>
            <span className="text-slate-dim">—</span>
            <span>{role === 'OWNER' ? 'Full access' : role === 'MANAGER' ? 'All except delete store' : 'Record sales only'}</span>
          </div>
        ))}
      </div>

      {showForm && (
        <div className="card p-5 mb-5 animate-fade-in">
          <h3 className="text-sm font-semibold text-slate-text mb-4">Add a staff member</h3>
          <form onSubmit={handleAdd} className="space-y-3">
            <div>
              <label htmlFor="staff-email" className="label">Their email address</label>
              <input id="staff-email" type="email" className="input" placeholder="staff@example.com"
                value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required />
              <p className="text-xs text-slate-dim mt-1">They must already have a VendorIQ account.</p>
            </div>
            <div>
              <label htmlFor="staff-role" className="label">Role</label>
              <select id="staff-role" className="input" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                <option value="CASHIER">Cashier — Record sales only</option>
                <option value="MANAGER">Manager — All except delete store</option>
              </select>
            </div>
            <button type="submit" disabled={saving} className="btn-primary w-full">
              {saving ? 'Adding...' : 'Add staff member'}
            </button>
          </form>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[1,2].map(i => <div key={i} className="card h-20 animate-pulse" />)}</div>
      ) : staff.length === 0 ? (
        <div className="card p-10 text-center">
          <Users size={32} className="text-slate-dim mx-auto mb-3" />
          <p className="text-slate-muted text-sm">No staff added yet.</p>
          <p className="text-xs text-slate-dim mt-1">Add team members to give them access to this store.</p>
        </div>
      ) : (
        <div className="card divide-y divide-navy-700">
          {staff.map(member => {
            const meta = ROLE_META[member.role] || ROLE_META.CASHIER
            return (
              <div key={member.id} className="px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-brand-50 dark:bg-brand-500/15 flex items-center justify-center flex-shrink-0">
                      <span className="text-sm font-bold text-brand-600 dark:text-brand-400">{member.user.name?.[0]?.toUpperCase()}</span>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-text">{member.user.name}</p>
                      <p className="text-xs text-slate-dim">{member.user.email}</p>
                      <p className="text-xs text-slate-dim mt-0.5">Added {formatDate(member.created_at)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className={`badge ${meta.color}`}>{meta.label}</span>
                    {member.role !== 'OWNER' && (
                      <>
                        <button onClick={() => { setEditingId(member.id); setEditRole(member.role) }}
                          className="p-1.5 text-slate-dim hover:text-slate-text transition-colors">
                          <Edit2 size={14} />
                        </button>
                        <button onClick={() => handleRemove(member)}
                          className="p-1.5 text-slate-dim hover:text-red-500 dark:hover:text-red-400 transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
                {editingId === member.id && (
                  <div className="mt-3 flex gap-2 animate-fade-in">
                    <select className="input flex-1 py-2 text-sm" value={editRole} onChange={e => setEditRole(e.target.value)}>
                      <option value="CASHIER">Cashier</option>
                      <option value="MANAGER">Manager</option>
                    </select>
                    <button onClick={() => handleUpdateRole(member.id)} disabled={saving} className="btn-primary text-sm py-2">
                      {saving ? '...' : 'Save'}
                    </button>
                    <button onClick={() => setEditingId(null)} className="btn-ghost text-sm py-2">Cancel</button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <ConfirmDialog
        open={!!pendingRemove}
        title={`Remove ${pendingRemove?.user.name} from this store?`}
        confirmLabel="Remove"
        loading={removing}
        onConfirm={confirmRemove}
        onCancel={() => setPendingRemove(null)}
      />
    </div>
  )
}
