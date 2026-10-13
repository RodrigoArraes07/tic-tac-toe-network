// Espelha a seção 7 do guia (docs/protocolo.md). Se o contrato mudar,
// mude primeiro o documento e depois este arquivo.

export type PlayerSymbol = 'X' | 'O'
export type Cell = PlayerSymbol | null
export type Board = Cell[]

export type PresenceStatus = 'FREE' | 'IN_MATCH'
export type MatchResult = 'WIN' | 'LOSS' | 'DRAW'
export type EndReason = 'LINE' | 'DRAW' | 'FORFEIT' | 'DISCONNECT'

export interface OnlineUser {
  username: string
  status: PresenceStatus
}

export interface LastMove {
  symbol: PlayerSymbol
  cell: number
}

export type ErrorCode =
  | 'INVALID_MESSAGE'
  | 'UNKNOWN_TYPE'
  | 'USER_OFFLINE'
  | 'USER_BUSY'
  | 'SELF_INVITE'
  | 'MATCH_NOT_FOUND'
  | 'NOT_A_PLAYER'
  | 'INVALID_STATE'
  | 'NOT_YOUR_TURN'
  | 'INVALID_CELL'
  | 'CELL_OCCUPIED'
  | 'STALE_STATE'
  | 'RATE_LIMITED'
  | 'INTERNAL'

/** Cliente → servidor */
export interface ClientPayloads {
  AUTH: { token: string }
  INVITE_SEND: { to_username: string }
  INVITE_CANCEL: { match_id: string }
  INVITE_RESPOND: { match_id: string; accept: boolean }
  MOVE: { match_id: string; cell: number; seq: number }
  FORFEIT: { match_id: string }
  MATCH_SYNC: { match_id: string }
}
export type ClientType = keyof ClientPayloads

/** Servidor → cliente */
export interface ServerPayloads {
  AUTH_OK: {
    user: { id: string; username: string }
    active_match_id: string | null
  }
  PRESENCE_SNAPSHOT: { users: OnlineUser[] }
  PRESENCE_UPDATE: { username: string; status: PresenceStatus | 'OFFLINE' }
  INVITE_SENT: { match_id: string; to_username: string; expires_in: number }
  INVITE_RECEIVED: { match_id: string; from_username: string; expires_in: number }
  INVITE_RESULT: { match_id: string; status: 'REJECTED' | 'EXPIRED' | 'CANCELLED' }
  MATCH_STARTED: {
    match_id: string
    you_are: PlayerSymbol
    opponent: string
    board: Board
    turn: PlayerSymbol
    seq: number
  }
  MATCH_STATE: {
    match_id: string
    board: Board
    turn: PlayerSymbol
    seq: number
    last_move: LastMove | null
    // NÃO estão no guia, mas são necessários para recarregar a página ou
    // reconectar no meio da partida (o cliente precisa saber seu símbolo).
    // Pedir ao Integrante A para incluir no MATCH_STATE.
    you_are?: PlayerSymbol
    opponent?: string
  }
  MATCH_ENDED: {
    match_id: string
    result: MatchResult
    reason: EndReason
    winning_line: number[] | null
    board: Board
  }
  OPPONENT_DISCONNECTED: { match_id: string; grace_seconds: number }
  OPPONENT_RECONNECTED: { match_id: string }
  ERROR: { code: ErrorCode; message: string }
}
export type ServerType = keyof ServerPayloads

export type ServerMessage = {
  [K in ServerType]: {
    type: K
    id: string
    ref: string | null
    ts: string
    payload: ServerPayloads[K]
  }
}[ServerType]

export type ServerMessageOf<K extends ServerType> = Extract<ServerMessage, { type: K }>
