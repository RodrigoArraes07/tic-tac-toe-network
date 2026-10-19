import { useState } from 'react';
import { useMatch } from '../context/match-context';
import { Modal } from './Modal';
import { resultDetail, resultTitle } from './result-text';

export function ResultDialog() {
  const { state, leaveMatch } = useMatch();
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);
  const end = state.end;
  const open = state.status === 'ended' && end !== null && dismissedFor !== state.matchId;

  return (
    <Modal open={open} title={end ? resultTitle(end.result) : ''}>
      {end && (
        <>
          <p>{resultDetail(end.result, end.reason)}</p>
          <div className="modal__actions">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setDismissedFor(state.matchId)}
            >
              Ver tabuleiro
            </button>
            <button type="button" className="btn" autoFocus onClick={leaveMatch}>
              Voltar ao lobby
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
