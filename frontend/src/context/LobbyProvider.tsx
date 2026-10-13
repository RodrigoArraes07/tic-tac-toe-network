import { useCallback, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react'
import { gameSocket } from '../socket'
import { initialLobby, lobbyReducer } from './lobby-reducer'
import { LobbyContext, type LobbyContextValue } from './lobby-context'
import { useToast } from './toast-context'

export function LobbyProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(lobbyReducer, initialLobby)
  const toast = useToast()
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    const offs = [
      gameSocket.subscribe('PRESENCE_SNAPSHOT', (m) =>
        dispatch({ type: 'snapshot', users: m.payload.users }),
      ),
      gameSocket.subscribe('PRESENCE_UPDATE', (m) =>
        dispatch({ type: 'presence', username: m.payload.username, status: m.payload.status }),
      ),
      gameSocket.subscribe('INVITE_SENT', (m) =>
        dispatch({
          type: 'invite_sent',
          matchId: m.payload.match_id,
          to: m.payload.to_username,
          expiresAt: Date.now() + m.payload.expires_in * 1000,
        }),
      ),
      gameSocket.subscribe('INVITE_RECEIVED', (m) =>
        dispatch({
          type: 'invite_received',
          matchId: m.payload.match_id,
          from: m.payload.from_username,
          expiresAt: Date.now() + m.payload.expires_in * 1000,
        }),
      ),
      gameSocket.subscribe('INVITE_RESULT', (m) => {
        const { match_id, status } = m.payload
        const mine = stateRef.current.outgoing
        if (mine && mine.matchId === match_id) {
          const text =
            status === 'REJECTED'
              ? `${mine.to} recusou o convite.`
              : status === 'EXPIRED'
                ? `${mine.to} não respondeu a tempo.`
                : 'Convite cancelado.'
          toast.push(text, 'info')
        }
        dispatch({ type: 'invite_closed', matchId: match_id })
      }),
      // Partida começou: qualquer convite pendente já foi resolvido.
      gameSocket.subscribe('MATCH_STARTED', () => dispatch({ type: 'invites_cleared' })),
      gameSocket.subscribe('ERROR', (m) => {
        const sending = stateRef.current.sending
        if (sending && m.ref === sending.id) dispatch({ type: 'send_failed' })
      }),
    ]
    return () => offs.forEach((off) => off())
  }, [toast])

  const sendInvite = useCallback((username: string) => {
    const id = gameSocket.send('INVITE_SEND', { to_username: username })
    if (id) dispatch({ type: 'sending', to: username, id })
  }, [])

  const cancelInvite = useCallback(() => {
    const outgoing = stateRef.current.outgoing
    if (!outgoing) return
    gameSocket.send('INVITE_CANCEL', { match_id: outgoing.matchId })
    dispatch({ type: 'invite_closed', matchId: outgoing.matchId })
  }, [])

  const respondInvite = useCallback((matchId: string, accept: boolean) => {
    gameSocket.send('INVITE_RESPOND', { match_id: matchId, accept })
    dispatch({ type: 'invite_closed', matchId })
  }, [])

  const value = useMemo<LobbyContextValue>(
    () => ({ state, sendInvite, cancelInvite, respondInvite }),
    [state, sendInvite, cancelInvite, respondInvite],
  )
  return <LobbyContext.Provider value={value}>{children}</LobbyContext.Provider>
}
