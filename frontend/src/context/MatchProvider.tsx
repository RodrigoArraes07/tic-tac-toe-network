import { useCallback, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { gameSocket } from '../socket'
import { MatchContext, type MatchContextValue } from './match-context'
import { initialMatch, matchReducer } from './match-reducer'

const PENDING_TIMEOUT_MS = 4000

export function MatchProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(matchReducer, initialMatch)
  const navigate = useNavigate()
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    const offs = [
      // Vale para o login e também para cada reconexão (RF11): se há partida
      // ativa, pede o estado completo e leva o usuário para ela.
      gameSocket.subscribe('AUTH_OK', (m) => {
        const active = m.payload.active_match_id
        const current = stateRef.current
        const resumeId = active ?? (current.status === 'playing' ? current.matchId : null)
        if (resumeId) gameSocket.send('MATCH_SYNC', { match_id: resumeId })
        if (active) navigate(`/match/${active}`)
      }),
      gameSocket.subscribe('MATCH_STARTED', (m) => {
        dispatch({ type: 'started', payload: m.payload, at: Date.now() })
        navigate(`/match/${m.payload.match_id}`)
      }),
      gameSocket.subscribe('MATCH_STATE', (m) => dispatch({ type: 'state', payload: m.payload, at: Date.now() })),
      gameSocket.subscribe('MATCH_ENDED', (m) => dispatch({ type: 'ended', payload: m.payload })),
      gameSocket.subscribe('OPPONENT_DISCONNECTED', (m) =>
        dispatch({ type: 'opponent_away', until: Date.now() + m.payload.grace_seconds * 1000 }),
      ),
      gameSocket.subscribe('OPPONENT_RECONNECTED', () => dispatch({ type: 'opponent_back' })),
      gameSocket.subscribe('ERROR', (m) => {
        const { pending, matchId } = stateRef.current
        if (pending && m.ref === pending.id) dispatch({ type: 'clear_pending', id: pending.id })
        // Clique duplicado ou mensagem atrasada: pede o estado oficial.
        if (m.payload.code === 'STALE_STATE' && matchId) {
          gameSocket.send('MATCH_SYNC', { match_id: matchId })
        }
      }),
    ]
    return () => offs.forEach((off) => off())
  }, [navigate])

  // Rede de segurança: se o servidor nunca responder à jogada, libera o tabuleiro.
  const pendingId = state.pending?.id
  useEffect(() => {
    if (!pendingId) return
    const t = setTimeout(() => dispatch({ type: 'clear_pending', id: pendingId }), PENDING_TIMEOUT_MS)
    return () => clearTimeout(t)
  }, [pendingId])

  const playMove = useCallback((cell: number) => {
    const s = stateRef.current
    if (s.status !== 'playing' || !s.matchId || s.pending) return
    if (s.turn !== s.you || s.board[cell] !== null) return
    const id = gameSocket.send('MOVE', { match_id: s.matchId, cell, seq: s.seq })
    if (id) dispatch({ type: 'pending', cell, id })
  }, [])

  const forfeit = useCallback(() => {
    const { matchId } = stateRef.current
    if (matchId) gameSocket.send('FORFEIT', { match_id: matchId })
  }, [])

  const syncMatch = useCallback((matchId: string) => {
    gameSocket.send('MATCH_SYNC', { match_id: matchId })
  }, [])

  const leaveMatch = useCallback(() => {
    dispatch({ type: 'reset' })
    navigate('/lobby')
  }, [navigate])

  const value = useMemo<MatchContextValue>(
    () => ({ state, playMove, forfeit, syncMatch, leaveMatch }),
    [state, playMove, forfeit, syncMatch, leaveMatch],
  )
  return <MatchContext.Provider value={value}>{children}</MatchContext.Provider>
}
