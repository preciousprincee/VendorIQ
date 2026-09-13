import { createContext, useContext, useState, useCallback } from 'react'
import api from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('viq_user')
      return stored ? JSON.parse(stored) : null
    } catch { return null }
  })

  const login = useCallback(async (email, password) => {
    const { data } = await api.post('/auth/login/', { email, password })
    localStorage.setItem('viq_token', data.token)
    localStorage.setItem('viq_user', JSON.stringify(data.user))
    setUser(data.user)
    return data
  }, [])

  const loginWithGoogle = useCallback(async (idToken) => {
    const { data } = await api.post('/auth/social/google/', { id_token: idToken })
    localStorage.setItem('viq_token', data.token)
    localStorage.setItem('viq_user', JSON.stringify(data.user))
    setUser(data.user)
    return data
  }, [])

  const register = useCallback(async (name, email, password, phone) => {
    const { data } = await api.post('/auth/register/', { name, email, password, phone })
    localStorage.setItem('viq_token', data.token)
    localStorage.setItem('viq_user', JSON.stringify(data.user))
    setUser(data.user)
    return data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('viq_token')
    localStorage.removeItem('viq_user')
    localStorage.removeItem('viq_store')
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, login, loginWithGoogle, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
