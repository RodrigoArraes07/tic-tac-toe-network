import { useCountdown } from '../hooks/useCountdown'
import { useLobby } from '../context/lobby-context'

export function OutgoingInvite() {
  const { state, cancelInvite } = useLobby()
  const left = useCountdown(state.outgoing?.expiresAt ?? null)
  if (!state.outgoing) return null

  return (
    <div className="banner" role="status">
      <span>
        Convite enviado para <strong>{state.outgoing.to}</strong>. Expira em {left}s.
      </span>
      <button type="button" className="btn btn--ghost btn--small" onClick={cancelInvite}>
        Cancelar convite
      </button>
    </div>
  )
}
