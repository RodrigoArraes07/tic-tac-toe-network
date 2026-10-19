import type {
  Board,
  EndReason,
  LastMove,
  MatchResult,
  PlayerSymbol,
  ServerPayloads,
} from '../protocol';

export interface MatchEnd {
  result: MatchResult;
  reason: EndReason;
  winningLine: number[] | null;
}

export interface MatchState {
  matchId: string | null;
  you: PlayerSymbol | null;
  opponent: string | null;
  board: Board;
  turn: PlayerSymbol | null;
  seq: number;
  lastMove: LastMove | null;
  status: 'idle' | 'playing' | 'ended';
  end: MatchEnd | null;
  /** Adversário caiu: até quando a janela de reconexão vale (timestamp em ms). */
  opponentAwayUntil: number | null;
  /** Quando o turno atual começou para este cliente (ms). Aproximação local: o protocolo não envia prazo. */
  turnStartedAt: number | null;
  /** Jogada enviada, esperando o servidor confirmar (seção 13.4). */
  pending: { cell: number; id: string } | null;
}

export const emptyBoard = (): Board => Array<null>(9).fill(null);

export const initialMatch: MatchState = {
  matchId: null,
  you: null,
  opponent: null,
  board: emptyBoard(),
  turn: null,
  seq: 0,
  lastMove: null,
  status: 'idle',
  end: null,
  opponentAwayUntil: null,
  turnStartedAt: null,
  pending: null,
};

export type MatchAction =
  | { type: 'started'; payload: ServerPayloads['MATCH_STARTED']; at: number }
  | { type: 'state'; payload: ServerPayloads['MATCH_STATE']; at: number }
  | { type: 'ended'; payload: ServerPayloads['MATCH_ENDED'] }
  | { type: 'opponent_away'; until: number }
  | { type: 'opponent_back'; at: number }
  | { type: 'pending'; cell: number; id: string }
  | { type: 'clear_pending'; id?: string }
  | { type: 'reset' };

/** O reducer só copia o que o servidor manda: nunca calcula vitória nem turno. */
export function matchReducer(state: MatchState, action: MatchAction): MatchState {
  switch (action.type) {
    case 'started': {
      const p = action.payload;
      return {
        ...initialMatch,
        matchId: p.match_id,
        you: p.you_are,
        opponent: p.opponent,
        board: p.board,
        turn: p.turn,
        seq: p.seq,
        status: 'playing',
        turnStartedAt: action.at,
      };
    }

    case 'state': {
      const p = action.payload;
      // Resposta a MATCH_SYNC de outra partida: recomeça do zero.
      const base = state.matchId === p.match_id ? state : initialMatch;
      return {
        ...base,
        matchId: p.match_id,
        you: p.you_are ?? base.you,
        opponent: p.opponent ?? base.opponent,
        board: p.board,
        turn: p.turn,
        seq: p.seq,
        lastMove: p.last_move,
        status: base.status === 'ended' ? 'ended' : 'playing',
        // Mesma jogada (ex.: resposta a MATCH_SYNC): mantém o relógio do turno.
        turnStartedAt:
          base.seq === p.seq && base.turnStartedAt !== null ? base.turnStartedAt : action.at,
        pending: null,
      };
    }

    case 'ended': {
      const p = action.payload;
      return {
        ...state,
        matchId: p.match_id,
        board: p.board,
        status: 'ended',
        end: { result: p.result, reason: p.reason, winningLine: p.winning_line },
        opponentAwayUntil: null,
        turnStartedAt: null,
        pending: null,
      };
    }

    case 'opponent_away':
      return { ...state, opponentAwayUntil: action.until };

    case 'opponent_back':
      // O servidor reinicia o turno de quem tem a vez com o prazo cheio.
      return {
        ...state,
        opponentAwayUntil: null,
        turnStartedAt: state.status === 'playing' ? action.at : state.turnStartedAt,
      };

    case 'pending':
      return { ...state, pending: { cell: action.cell, id: action.id } };

    case 'clear_pending':
      if (action.id && state.pending?.id !== action.id) return state;
      return { ...state, pending: null };

    case 'reset':
      return initialMatch;
  }
}
