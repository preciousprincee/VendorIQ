import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import api, { isNetworkError, CSRF_HEADERS } from '../lib/api'
import {
  setAccessToken, hasSessionHint, dropLegacyTokens, wipeLocalSession, invalidatePendingRefresh,
  markLogoutPending, isLogoutPending, clearLogoutPending,
} from '../lib/session'

import { track, reset as resetAnalytics } from '../lib/analytics'

const AuthContext = createContext(null)

// After a successful sign-in the SERVER has set the refresh token in an HttpOnly cookie; the response
// body carries only the short-lived access token, which is kept in memory (never written to storage).
// localStorage keeps just the non-secret "who is signed in" hint so the app can open offline.
function startSession(data) {
  invalidatePendingRefresh()   // a refresh already in flight belongs to the previous identity
  setAccessToken(data.token)
  dropLegacyTokens()
  clearLogoutPending()   // a fresh sign-in replaced the cookie, so any pending sign-out is obsolete
  localStorage.setItem('viq_user', JSON.stringify(data.user))
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('viq_user')
      return stored ? JSON.parse(stored) : null
    } catch { return null }
  })

  const login = useCallback(async (email, password) => {
    const { data } = await api.post('/auth/login/', { email, password })
    startSession(data)
    setUser(data.user)
    track('login', { method: 'email' })
    return data
  }, [])

  const loginWithGoogle = useCallback(async (idToken, referralCode) => {
    const { data } = await api.post('/auth/social/google/', { id_token: idToken, referred_by_code: referralCode || undefined })
    startSession(data)
    setUser(data.user)
    // sign_up is recorded by the server (it knows when it created the account); here only a repeat sign-in.
    if (!data.isNewAccount) track('login', { method: 'google' })
    return data
  }, [])

  const register = useCallback(async (name, email, password, phone, referralCode) => {
    const { data } = await api.post('/auth/register/', { name, email, password, phone, referred_by_code: referralCode || undefined })
    startSession(data)
    setUser(data.user)
    return data
  }, [])

  const logout = useCallback(() => {
    // A page script cannot delete an HttpOnly cookie, so signing out is a server call. If there is no
    // connection, remember to finish the job as soon as there is one (the cookie is still valid until then).
    api.post('/auth/logout/', {}, { headers: CSRF_HEADERS, timeout: 8000 })
      .catch((err) => { if (isNetworkError(err)) markLogoutPending() })
    wipeLocalSession()
    resetAnalytics()   // forget who this was; the next person on this device starts clean
    setUser(null)
  }, [])

  // Replaces the cached user with a server copy (verification status etc.).
  const applyUser = useCallback((nextUser) => {
    if (!nextUser) return
    localStorage.setItem('viq_user', JSON.stringify(nextUser))
    setUser(nextUser)
  }, [])

  const refreshUser = useCallback(async () => {
    const { data } = await api.get('/auth/me/')
    applyUser(data.user)
    return data.user
  }, [applyUser])

  // The user object is cached in localStorage, so on every app load ask the server for the truth - that is
  // how accounts created before email/phone verification existed get sent to the verification screen. (The
  // request interceptor first trades the cookie for an access token; offline, this just fails quietly and the
  // app carries on with the cached user.)
  useEffect(() => {
    if (hasSessionHint()) refreshUser().catch(() => {})
  }, [refreshUser])

  // Finish a sign-out that happened while offline.
  useEffect(() => {
    const finish = () => {
      if (!isLogoutPending()) return
      api.post('/auth/logout/', {}, { headers: CSRF_HEADERS, timeout: 8000 })
        .then(clearLogoutPending)
        .catch(() => { /* still offline: try again on the next 'online' event */ })
    }
    finish()
    window.addEventListener('online', finish)
    return () => window.removeEventListener('online', finish)
  }, [])

  // Edit-profile (name/phone only - see backend UpdateProfileSerializer for
  // why email isn't editable here). Used by ProfilePage's edit form.
  const updateProfile = useCallback(async (updates) => {
    const { data } = await api.patch('/auth/me/', updates)
    applyUser(data.user)
    return data.user
  }, [applyUser])

  return (
    <AuthContext.Provider value={{ user, login, loginWithGoogle, register, logout, updateProfile, applyUser, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
