// Servidor FALSO para desenvolver o front sem o backend (guia, seção 15.2).
// Fala o mesmo protocolo da seção 7: REST + WebSocket na porta 8000.
//   npm run mock   (em outro terminal)   e   npm run dev
import http from 'node:http';
import { WebSocketServer } from 'ws';

const PORT = 8000;
const INVITE_S = Number(process.env.INVITE_TIMEOUT_S ?? 30);
const GRACE_S = Number(process.env.RECONNECT_GRACE_S ?? 30);
let turnS = Number(process.env.TURN_TIMEOUT_S ?? 30); // 30 s por turno (protocolo 7.4)
const LINES = [
  [0, 1, 2],
  [3, 4, 5],
  [6, 7, 8],
  [0, 3, 6],
  [1, 4, 7],
  [2, 5, 8],
  [0, 4, 8],
  [2, 4, 6],
];

const users = new Map(); // username -> {password, stats}
const sockets = new Map(); // username -> ws
const matches = new Map(); // id -> match
let seqId = 1;
const finished = []; // partidas encerradas (para /api/matches/history)
const loginFailures = new Map(); // username -> timestamps (limite de 5/min, T04)

// Validação dos payloads, no mesmo rigor do protocol.py (StrictStr/StrictInt/StrictBool).
const SCHEMAS = {
  AUTH: { token: 'string' },
  INVITE_SEND: { to_username: 'string' },
  INVITE_CANCEL: { match_id: 'string' },
  INVITE_RESPOND: { match_id: 'string', accept: 'boolean' },
  MOVE: { match_id: 'string', cell: 'integer', seq: 'integer' },
  FORFEIT: { match_id: 'string' },
  MATCH_SYNC: { match_id: 'string' },
};
const payloadOk = (type, p) =>
  p !== null &&
  typeof p === 'object' &&
  !Array.isArray(p) &&
  Object.entries(SCHEMAS[type]).every(([k, t]) =>
    t === 'integer' ? Number.isInteger(p[k]) : typeof p[k] === t,
  );

const json = (res, status, body) => {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(body === undefined ? '' : JSON.stringify(body));
};
const readBody = (req) =>
  new Promise((resolve) => {
    let raw = '';
    req.on('data', (c) => (raw += c));
    req.on('end', () => {
      try {
        resolve(JSON.parse(raw || '{}'));
      } catch {
        resolve(null);
      }
    });
  });
const userFromAuth = (req) => {
  const t = (req.headers.authorization ?? '').replace('Bearer ', '');
  return t.startsWith('mock.') && users.has(t.slice(5)) ? t.slice(5) : null;
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  if (req.method === 'POST' && url.pathname === '/api/auth/register') {
    const b = await readBody(req);
    // Corpo malformado (campo ausente/tipo errado): 422 do FastAPI, `detail` é uma LISTA.
    const bad = ['username', 'password'].filter((k) => typeof b?.[k] !== 'string');
    if (bad.length)
      return json(res, 422, {
        detail: bad.map((k) => ({ type: 'missing', loc: ['body', k], msg: 'Field required' })),
      });
    const name = b.username.toLowerCase();
    if (!/^[a-z0-9_]{3,20}$/.test(name) || b.password.length < 8 || b.password.length > 72) {
      return json(res, 422, {
        detail: 'Dados inválidos: usuário de 3 a 20 caracteres [a-zA-Z0-9_] e senha de 8 a 72.',
      });
    }
    if (users.has(name)) return json(res, 409, { detail: 'Esse username já está em uso.' });
    users.set(name, { password: b.password, stats: { wins: 0, draws: 0, losses: 0, points: 0 } });
    return json(res, 201, { id: name, username: name });
  }
  if (req.method === 'POST' && url.pathname === '/api/auth/login') {
    const b = await readBody(req);
    const name = String(b?.username ?? '').toLowerCase();
    const recent = (loginFailures.get(name) ?? []).filter((t) => Date.now() - t < 60_000);
    if (recent.length >= 5)
      return json(res, 429, { detail: 'Muitas tentativas de login. Aguarde um minuto.' });
    if (users.get(name)?.password !== b?.password) {
      loginFailures.set(name, [...recent, Date.now()]);
      return json(res, 401, { detail: 'Usuário ou senha inválidos.' });
    }
    return json(res, 200, {
      access_token: 'mock.' + name,
      token_type: 'bearer',
      expires_in: 3600,
      user: { id: name, username: name },
    });
  }
  if (req.method === 'GET' && url.pathname === '/api/me') {
    const u = userFromAuth(req);
    return u
      ? json(res, 200, { id: u, username: u, stats: users.get(u).stats })
      : json(res, 401, { detail: 'Não autenticado.' });
  }
  if (req.method === 'GET' && url.pathname === '/api/matches/history') {
    const u = userFromAuth(req);
    if (!u) return json(res, 401, { detail: 'Não autenticado.' });
    const rows = finished
      .filter((m) => m.x === u || m.o === u)
      .slice(-20)
      .reverse()
      .map((m) => ({
        id: m.id,
        player_x_id: m.x,
        player_o_id: m.o,
        winner_id: m.winner,
        reason: m.reason,
        ended_at: m.endedAt,
      }));
    return json(res, 200, rows);
  }
  if (req.method === 'GET' && url.pathname === '/api/ranking') {
    if (!userFromAuth(req)) return json(res, 401, { detail: 'Não autenticado.' });
    const rows = [...users.entries()]
      .map(([username, u]) => ({ username, ...u.stats }))
      .sort((a, b) => b.points - a.points || b.wins - a.wins || a.losses - b.losses)
      .slice(0, Number(url.searchParams.get('limit') ?? 20))
      .map((r, i) => ({ position: i + 1, ...r }));
    return json(res, 200, rows);
  }
  // Gancho SÓ do mock: encurta o tempo de turno para testar TIMEOUT sem esperar 30 s.
  if (req.method === 'POST' && url.pathname === '/api/_mock/config') {
    const b = await readBody(req);
    if (Number.isFinite(b?.turn_timeout_s) && b.turn_timeout_s > 0) turnS = b.turn_timeout_s;
    return json(res, 200, { turn_timeout_s: turnS });
  }
  if (url.pathname === '/api/health') return json(res, 200, { status: 'ok', db: 'mock' });
  json(res, 404, { detail: 'not found' });
});

const wss = new WebSocketServer({ server, path: '/ws' });

const env = (type, payload, ref = null) =>
  JSON.stringify({ type, id: crypto.randomUUID(), ref, ts: new Date().toISOString(), payload });
const sendTo = (name, type, payload, ref) => {
  const ws = sockets.get(name);
  if (ws?.readyState === 1) ws.send(env(type, payload, ref));
};
const broadcast = (type, payload) =>
  sockets.forEach((ws) => ws.readyState === 1 && ws.send(env(type, payload)));
const activeMatchOf = (name) =>
  [...matches.values()].find((m) => m.status === 'IN_PROGRESS' && (m.x === name || m.o === name));
const pendingOf = (name) =>
  [...matches.values()].find((m) => m.status === 'PENDING' && (m.x === name || m.o === name));
const statusOf = (name) => (activeMatchOf(name) ? 'IN_MATCH' : 'FREE');
// Após cada jogada: sem you_are/opponent. Em resposta a MATCH_SYNC: com eles (protocolo 7.4).
const stateOf = (m, me, withIdentity = false) => ({
  match_id: m.id,
  board: m.board,
  turn: m.turn,
  seq: m.seq,
  last_move: m.last,
  ...(withIdentity ? { you_are: m.x === me ? 'X' : 'O', opponent: m.x === me ? m.o : m.x } : {}),
});
const winnerOf = (b) => {
  for (const l of LINES)
    if (b[l[0]] && b[l[0]] === b[l[1]] && b[l[0]] === b[l[2]]) return { s: b[l[0]], line: l };
  return null;
};

function endMatch(m, winnerName, reason, line = null) {
  if (m.status !== 'IN_PROGRESS') return;
  m.status = 'FINISHED';
  clearTimeout(m.grace);
  clearTimeout(m.turnTimer);
  Object.assign(m, { winner: winnerName, reason, endedAt: new Date().toISOString() });
  finished.push(m);
  for (const name of [m.x, m.o]) {
    const st = users.get(name).stats;
    const result = winnerName === null ? 'DRAW' : winnerName === name ? 'WIN' : 'LOSS';
    if (result === 'WIN') {
      st.wins++;
      st.points += 3;
    } else if (result === 'DRAW') {
      st.draws++;
      st.points += 1;
    } else st.losses++;
    sendTo(name, 'MATCH_ENDED', {
      match_id: m.id,
      result,
      reason,
      winning_line: line,
      board: m.board,
    });
    broadcast('PRESENCE_UPDATE', { username: name, status: 'FREE' });
  }
}

// 30 s por turno: estourou, vence o adversário com reason TIMEOUT.
function armTurnTimer(m) {
  clearTimeout(m.turnTimer);
  m.turnTimer = setTimeout(() => {
    const loser = m.turn === 'X' ? m.x : m.o;
    endMatch(m, loser === m.x ? m.o : m.x, 'TIMEOUT');
  }, turnS * 1000);
}

function closeInvite(m, status) {
  m.status = status;
  clearTimeout(m.timer);
  sendTo(m.x, 'INVITE_RESULT', { match_id: m.id, status });
  sendTo(m.o, 'INVITE_RESULT', { match_id: m.id, status });
}

wss.on('connection', (ws) => {
  let me = null;
  const authTimer = setTimeout(() => !me && ws.close(4401), 5000);
  const err = (code, message, ref) => ws.send(env('ERROR', { code, message }, ref));

  ws.on('message', (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return err('INVALID_MESSAGE', 'Mensagem inválida.');
    }
    const readableId = typeof msg?.id === 'string' ? msg.id : undefined; // `ref` só vem quando o id é legível
    if (!msg || typeof msg !== 'object' || Array.isArray(msg) || typeof msg.type !== 'string') {
      return err('INVALID_MESSAGE', 'Mensagem inválida.', readableId);
    }
    const { type, id } = msg;
    const payload = msg.payload ?? {};
    if (!me && type !== 'AUTH') return ws.close(4401);
    if (!(type in SCHEMAS)) return err('UNKNOWN_TYPE', `Tipo desconhecido: ${type}.`, readableId);
    if (!payloadOk(type, payload)) return err('INVALID_MESSAGE', 'Payload inválido.', readableId);
    if (me && type === 'AUTH') return err('INVALID_STATE', 'Esta conexão já está autenticada.', id);

    if (type === 'AUTH') {
      const t = String(payload.token ?? '');
      if (!t.startsWith('mock.') || !users.has(t.slice(5))) return ws.close(4401);
      me = t.slice(5);
      clearTimeout(authTimer);
      const old = sockets.get(me);
      if (old && old !== ws) old.close(4001);
      sockets.set(me, ws);
      const active = activeMatchOf(me);
      if (active) {
        clearTimeout(active.grace);
        sendTo(me === active.x ? active.o : active.x, 'OPPONENT_RECONNECTED', {
          match_id: active.id,
        });
      }
      ws.send(
        env('AUTH_OK', { user: { id: me, username: me }, active_match_id: active?.id ?? null }),
      );
      ws.send(
        env('PRESENCE_SNAPSHOT', {
          users: [...sockets.keys()].map((u) => ({ username: u, status: statusOf(u) })),
        }),
      );
      broadcast('PRESENCE_UPDATE', { username: me, status: statusOf(me) });
      return;
    }
    if (type === 'INVITE_SEND') {
      const to = String(payload.to_username ?? '');
      if (to === me) return err('SELF_INVITE', 'Você não pode convidar a si mesmo.', id);
      if (!sockets.has(to)) return err('USER_OFFLINE', `${to} não está online.`, id);
      if (activeMatchOf(me) || pendingOf(me) || activeMatchOf(to) || pendingOf(to))
        return err('USER_BUSY', 'Um dos jogadores já está em partida ou convite.', id);
      const m = {
        id: 'm' + seqId++,
        x: me,
        o: to,
        status: 'PENDING',
        board: Array(9).fill(null),
        turn: 'X',
        seq: 0,
        last: null,
      };
      matches.set(m.id, m);
      m.timer = setTimeout(
        () => m.status === 'PENDING' && closeInvite(m, 'EXPIRED'),
        INVITE_S * 1000,
      );
      sendTo(me, 'INVITE_SENT', { match_id: m.id, to_username: to, expires_in: INVITE_S }, id);
      sendTo(to, 'INVITE_RECEIVED', { match_id: m.id, from_username: me, expires_in: INVITE_S });
      return;
    }
    const m = matches.get(payload.match_id);
    if (!m) return err('MATCH_NOT_FOUND', 'Partida não encontrada.', id);
    if (m.x !== me && m.o !== me)
      return err('NOT_A_PLAYER', 'Você não participa desta partida.', id);

    if (type === 'INVITE_CANCEL' && m.status === 'PENDING' && m.x === me)
      return closeInvite(m, 'CANCELLED');
    if (type === 'INVITE_RESPOND' && m.status === 'PENDING' && m.o === me) {
      if (!payload.accept) return closeInvite(m, 'REJECTED');
      clearTimeout(m.timer);
      m.status = 'IN_PROGRESS';
      for (const n of [m.x, m.o]) {
        sendTo(n, 'MATCH_STARTED', {
          match_id: m.id,
          you_are: m.x === n ? 'X' : 'O',
          opponent: m.x === n ? m.o : m.x,
          board: m.board,
          turn: m.turn,
          seq: m.seq,
        });
        broadcast('PRESENCE_UPDATE', { username: n, status: 'IN_MATCH' });
      }
      armTurnTimer(m);
      return;
    }
    if (type === 'MATCH_SYNC') return ws.send(env('MATCH_STATE', stateOf(m, me, true), id));
    if (m.status !== 'IN_PROGRESS')
      return err('INVALID_STATE', 'Ação incompatível com o estado da partida.', id);

    if (type === 'FORFEIT') return endMatch(m, me === m.x ? m.o : m.x, 'FORFEIT');
    if (type === 'MOVE') {
      const sym = m.x === me ? 'X' : 'O';
      if (m.turn !== sym) return err('NOT_YOUR_TURN', 'Aguarde sua vez.', id);
      if (!Number.isInteger(payload.cell) || payload.cell < 0 || payload.cell > 8)
        return err('INVALID_CELL', 'Casa inválida.', id);
      if (payload.seq !== m.seq) {
        err('STALE_STATE', 'Estado desatualizado.', id);
        return;
      }
      if (m.board[payload.cell]) return err('CELL_OCCUPIED', 'Essa casa já está ocupada.', id);
      m.board[payload.cell] = sym;
      m.seq++;
      m.last = { symbol: sym, cell: payload.cell };
      const w = winnerOf(m.board);
      if (w) {
        m.turn = sym;
        for (const n of [m.x, m.o]) sendTo(n, 'MATCH_STATE', stateOf(m, n), n === me ? id : null);
        return endMatch(m, me, 'LINE', w.line);
      }
      if (m.board.every(Boolean)) {
        for (const n of [m.x, m.o]) sendTo(n, 'MATCH_STATE', stateOf(m, n), n === me ? id : null);
        return endMatch(m, null, 'DRAW');
      }
      m.turn = sym === 'X' ? 'O' : 'X';
      armTurnTimer(m);
      for (const n of [m.x, m.o]) sendTo(n, 'MATCH_STATE', stateOf(m, n), n === me ? id : null);
    }
  });

  ws.on('close', () => {
    clearTimeout(authTimer);
    if (!me || sockets.get(me) !== ws) return;
    sockets.delete(me);
    broadcast('PRESENCE_UPDATE', { username: me, status: 'OFFLINE' });
    const p = pendingOf(me);
    if (p) closeInvite(p, 'CANCELLED');
    const a = activeMatchOf(me);
    if (a) {
      const other = a.x === me ? a.o : a.x;
      sendTo(other, 'OPPONENT_DISCONNECTED', { match_id: a.id, grace_seconds: GRACE_S });
      a.grace = setTimeout(() => endMatch(a, other, 'DISCONNECT'), GRACE_S * 1000);
    }
  });
});

server.listen(PORT, () => console.log(`[mock] http://localhost:${PORT}  (REST + WS /ws)`));
