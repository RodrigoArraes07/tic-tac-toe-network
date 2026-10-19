import type { OnlineUser, PresenceStatus } from '../protocol';

export interface OutgoingInvite {
  matchId: string;
  to: string;
  expiresAt: number;
}

export interface IncomingInvite {
  matchId: string;
  from: string;
  expiresAt: number;
}

export interface LobbyState {
  users: OnlineUser[];
  outgoing: OutgoingInvite | null;
  incoming: IncomingInvite[];
  /** INVITE_SEND enviado, esperando INVITE_SENT ou ERROR. */
  sending: { to: string; id: string } | null;
}

export const initialLobby: LobbyState = { users: [], outgoing: null, incoming: [], sending: null };

export type LobbyAction =
  | { type: 'snapshot'; users: OnlineUser[] }
  | { type: 'presence'; username: string; status: PresenceStatus | 'OFFLINE' }
  | { type: 'sending'; to: string; id: string }
  | { type: 'send_failed' }
  | { type: 'invite_sent'; matchId: string; to: string; expiresAt: number }
  | { type: 'invite_received'; matchId: string; from: string; expiresAt: number }
  | { type: 'invite_closed'; matchId: string }
  | { type: 'invites_cleared' };

const byName = (a: OnlineUser, b: OnlineUser) => a.username.localeCompare(b.username);

export function lobbyReducer(state: LobbyState, action: LobbyAction): LobbyState {
  switch (action.type) {
    case 'snapshot':
      return { ...state, users: [...action.users].sort(byName) };

    case 'presence': {
      const others = state.users.filter((u) => u.username !== action.username);
      if (action.status === 'OFFLINE') return { ...state, users: others };
      return {
        ...state,
        users: [...others, { username: action.username, status: action.status }].sort(byName),
      };
    }

    case 'sending':
      return { ...state, sending: { to: action.to, id: action.id } };

    case 'send_failed':
      return { ...state, sending: null };

    case 'invite_sent':
      return {
        ...state,
        sending: null,
        outgoing: { matchId: action.matchId, to: action.to, expiresAt: action.expiresAt },
      };

    case 'invite_received':
      return {
        ...state,
        incoming: [
          ...state.incoming.filter((i) => i.matchId !== action.matchId),
          { matchId: action.matchId, from: action.from, expiresAt: action.expiresAt },
        ],
      };

    case 'invite_closed':
      return {
        ...state,
        outgoing: state.outgoing?.matchId === action.matchId ? null : state.outgoing,
        incoming: state.incoming.filter((i) => i.matchId !== action.matchId),
      };

    case 'invites_cleared':
      return { ...state, outgoing: null, incoming: [], sending: null };
  }
}
