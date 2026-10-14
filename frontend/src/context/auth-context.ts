import { createContext, useContext } from 'react'
import type { User } from '../api'
import type { SocketStatus } from '../socket'

export interface AuthContextValue {
  /** loading: validando o token salvo na aba; anon: sem sessão; authed: logado */
  status: 'loading' | 'anon' | 'authed'
  user: User | null
  socketStatus: SocketStatus
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => void
  /** Depois do 4001: usar esta aba (derruba a outra). */
  resumeSocket: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth fora do AuthProvider')
  return value
}
