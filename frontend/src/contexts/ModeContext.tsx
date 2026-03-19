import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getMode, setMode as setModeApi } from '../api/hyperliquid'

const MODE_STORAGE_KEY = 'tradelab-mode'
export type UITradingMode = 'paper' | 'live'
type BackendMode = 'planning' | 'live'

const normalizeMode = (value?: string | null): UITradingMode => value === 'paper' ? 'paper' : 'live'
const toBackendMode = (mode: UITradingMode): BackendMode => mode === 'paper' ? 'planning' : 'live'

interface ModeContextType {
  mode: UITradingMode
  toggleMode: () => Promise<void>
  isLoading: boolean
}

const ModeContext = createContext<ModeContextType | null>(null)

export function ModeProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [mode, setModeState] = useState<UITradingMode>(() => {
    if (typeof window === 'undefined') return 'live'
    return normalizeMode(window.localStorage.getItem(MODE_STORAGE_KEY))
  })
  const [isLoading, setIsLoading] = useState(false)

  // Sync with backend on mount
  useEffect(() => {
    getMode()
      .then((res) => {
        const backendMode = normalizeMode(res.data?.mode)
        setModeState((current) => {
          if (current !== backendMode) {
            if (typeof window !== 'undefined') {
              window.localStorage.setItem(MODE_STORAGE_KEY, backendMode)
            }
            return backendMode
          }
          return current
        })
      })
      .catch(() => {})
  }, [])

  const toggleMode = useCallback(async () => {
    const nextMode: UITradingMode = mode === 'paper' ? 'live' : 'paper'
    const previousMode = mode

    // Optimistic update
    setModeState(nextMode)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(MODE_STORAGE_KEY, nextMode)
    }

    setIsLoading(true)
    try {
      await setModeApi(toBackendMode(nextMode))
      await queryClient.invalidateQueries({ queryKey: ['mode'] })
    } catch (error) {
      // Revert on error
      setModeState(previousMode)
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(MODE_STORAGE_KEY, previousMode)
      }
      throw error
    } finally {
      setIsLoading(false)
    }
  }, [mode, queryClient])

  return (
    <ModeContext.Provider value={{ mode, toggleMode, isLoading }}>
      {children}
    </ModeContext.Provider>
  )
}

export function useMode() {
  const context = useContext(ModeContext)
  if (!context) {
    throw new Error('useMode must be used within a ModeProvider')
  }
  return context
}
