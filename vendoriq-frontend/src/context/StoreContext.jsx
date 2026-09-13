import { createContext, useContext, useState, useCallback } from 'react'

const StoreContext = createContext(null)

export function StoreProvider({ children }) {
  const [activeStore, setActiveStore] = useState(() => {
    try {
      const stored = localStorage.getItem('viq_store')
      return stored ? JSON.parse(stored) : null
    } catch { return null }
  })

  const selectStore = useCallback((store) => {
    localStorage.setItem('viq_store', JSON.stringify(store))
    setActiveStore(store)
  }, [])

  const clearStore = useCallback(() => {
    localStorage.removeItem('viq_store')
    setActiveStore(null)
  }, [])

  return (
    <StoreContext.Provider value={{ activeStore, selectStore, clearStore }}>
      {children}
    </StoreContext.Provider>
  )
}

export const useStore = () => {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used within StoreProvider')
  return ctx
}
