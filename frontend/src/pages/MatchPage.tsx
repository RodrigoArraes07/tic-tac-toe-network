import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Board } from '../components/Board'
import { Modal } from '../components/Modal'
import { ResultDialog } from '../components/ResultDialog'
import { resultDetail, resultTitle } from '../components/result-text'
import { useMatch } from '../context/match-context'
import { useCountdown } from '../hooks/useCountdown'
import { useSocketStatus } from '../hooks/useSocketStatus'

export function MatchPage() {
  const { id } = useParams()
  const { state, playMove, forfeit, syncMatch, leaveMatch } = useMatch()
  const socketStatus = useSocketStatus()
  const [confirmingForfeit, setConfirmingForfeit] = useState(false)
  const awayLeft = useCountdown(state.opponentAwayUntil)

  // Abriu /match/:id direto (ou recarregou): pede o estado oficial ao servidor.
  useEffect(() => {
    if (id && socketStatus === 'open' && state.matchId !== id) syncMatch(id)
  }, [id, socketStatus, state.matchId, syncMatch])

  if (state.status === 'idle' || state.matchId !== id) {
    return (
      <div className="sheet">
        <p>Carregando partida…</p>
        <p className="muted">
          Se isso demorar, <Link to="/lobby">volte ao lobby</Link>.
        </p>
      </div>
    )
  }

  const playing = state.status === 'playing'
  const myTurn = playing && state.turn !== null && state.turn === state.you
  const known = state.you !== null

  let headline: string
  if (state.status === 'ended' && state.end) headline = resultTitle(state.end.result)
  else if (!known) headline = 'Sincronizando partida…'
  else if (myTurn) headline = 'Sua vez'
  else headline = `Vez de ${state.opponent ?? 'o adversário'}`

  return (
    <div className="match">
      <header className="match__head">
        <h1 className="match__turn" aria-live="polite">
          {headline}
        </h1>
        <p className="muted">
          {state.status === 'ended' && state.end ? (
            resultDetail(state.end.result, state.end.reason)
          ) : known ? (
            <>
              Você joga com <strong className={`sym sym--${state.you}`}>{state.you}</strong> contra{' '}
              <strong>{state.opponent ?? 'o adversário'}</strong>
            </>
          ) : (
            'Aguardando o servidor informar seu símbolo.'
          )}
        </p>
      </header>

      {playing && state.opponentAwayUntil !== null && (
        <div className="banner banner--warn" role="status">
          {state.opponent ?? 'Seu adversário'} perdeu a conexão. Ele tem {awayLeft}s para voltar antes de a partida acabar.
        </div>
      )}

      <Board
        board={state.board}
        you={state.you}
        canPlay={myTurn && known}
        pendingCell={state.pending?.cell ?? null}
        winningLine={state.end?.winningLine ?? null}
        onPlay={playMove}
      />

      <div className="match__actions">
        {playing ? (
          <button type="button" className="btn btn--danger" onClick={() => setConfirmingForfeit(true)}>
            Desistir
          </button>
        ) : (
          <button type="button" className="btn" onClick={leaveMatch}>
            Voltar ao lobby
          </button>
        )}
      </div>

      <Modal open={confirmingForfeit} title="Desistir da partida?" onEscape={() => setConfirmingForfeit(false)}>
        <p>Seu adversário vence e a derrota entra no seu ranking.</p>
        <div className="modal__actions">
          <button type="button" className="btn btn--ghost" autoFocus onClick={() => setConfirmingForfeit(false)}>
            Continuar jogando
          </button>
          <button
            type="button"
            className="btn btn--danger"
            onClick={() => {
              setConfirmingForfeit(false)
              forfeit()
            }}
          >
            Desistir
          </button>
        </div>
      </Modal>

      <ResultDialog />
    </div>
  )
}
