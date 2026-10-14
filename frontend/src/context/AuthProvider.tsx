import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore, type User } from '../api'
import { useSocketStatus } from '../hooks/useSocketStatus'
import { gameSocket } from '../socket'
import { AuthContext, type AuthContextValue } from './auth-context'
import { useToast } from './toast-context'

type Status = AuthContextValue['status']

export function AuthProvider({ children }: { children: ReactNode }) {
  const toast = useToast()
  const socketStatus = useSocketStatus()
  const [token, setToken] = useState<string | null>(() => tokenStore.get())
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState<Status>(() => (tokenStore.get() ? 'loading' : 'anon'))

  const clearSession = useCallback(() => {
    tokenStore.clear()
    gameSocket.disconnect()
    setToken(null)
    setUser(null)
    setStatus('anon')
  }, [])

  const expireSession = useCallback(() => {
    clearSession()
    toast.push('Sua sessão expirou. Entre de novo.', 'info')
  }, [clearSession, toast])

  // Token salvo na aba (F5): valida buscando o usuário.
  useEffect(() => {
    if (!token || user) return
    let cancelled = false
    api
      .me()
      .then((me) => {
        if (cancelled) return
        setUser(me)
        setStatus('authed')
      })
      .catch(() => {
        if (!cancelled) clearSession()
      })
    return () => {
      cancelled = true
    }
  }, [token, user, clearSession])

  // Abre o WebSocket quando há sessão. connect() é idempotente (StrictMode).
  useEffect(() => {
    if (status === 'authed' && token) gameSocket.connect(token)
  }, [status, token])

  // Token recusado: 401 no REST ou close 4401 no WebSocket.
  useEffect(() => {
    setUnauthorizedHandler(expireSession)
    const off = gameSocket.onAuthFailed(expireSession)
    return () => {
      setUnauthorizedHandler(() => {})
      off()
    }
  }, [expireSession])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password)
    tokenStore.set(res.access_token)
    setToken(res.access_token)
    setUser(res.user)
    setStatus('authed')
  }, [])

  const register = useCallback(async (username: string, password: string) => {
    await api.register(username, password)
  }, [])

  const resumeSocket = useCallback(() => gameSocket.resume(), [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, socketStatus, login, register, logout: clearSession, resumeSocket }),
    [status, user, socketStatus, login, register, clearSession, resumeSocket],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
