import { useCountdown } from '../hooks/useCountdown'
import { useLobby } from '../context/lobby-context'
import { Modal } from './Modal'

/** Convite recebido. Fica no Layout para aparecer em qualquer tela logada. */
export function InviteDialog() {
  const { state, respondInvite } = useLobby()
  const invite = state.incoming[0] ?? null
  const left = useCountdown(invite?.expiresAt ?? null)

  return (
    <Modal open={invite !== null} title="Convite para jogar">
      {invite && (
        <>
          <p>
            <strong>{invite.from}</strong> chamou você para uma partida. Você joga com O e ele começa.
          </p>
          <p className="muted">Expira em {left}s</p>
          <div className="modal__actions">
            <button type="button" className="btn btn--ghost" onClick={() => respondInvite(invite.matchId, false)}>
              Recusar
            </button>
            <button type="button" className="btn" autoFocus onClick={() => respondInvite(invite.matchId, true)}>
              Aceitar e jogar
            </button>
          </div>
        </>
      )}
    </Modal>
  )
}
