// Testes de contrato: falam o protocolo direto (REST + WebSocket), sem UI.
// Servem para conferir que o mock e o back-end real respondem igual (docs/protocolo.md).
import { expect, test, type APIRequestContext } from '@playwright/test';
import WebSocket from 'ws';
import { cell, playMoves, startMatch, twoPlayersInLobby, uniqueName } from './helpers';

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:5173';
const WS_URL = `${BASE.replace(/^http/, 'ws')}/ws`;

async function createUser(request: APIRequestContext) {
  const username = uniqueName('ct');
  const password = 'senha-forte-123';
  const reg = await request.post('/api/auth/register', { data: { username, password } });
  expect(reg.status()).toBe(201);
  const registered = await reg.json();
  const login = await (
    await request.post('/api/auth/login', { data: { username, password } })
  ).json();
  return { username, registered, login, token: login.access_token as string };
}

/** Abre o WS, envia AUTH e devolve helpers para conversar e esperar respostas. */
async function openAuthenticated(token: string) {
  const ws = new WebSocket(WS_URL, { rejectUnauthorized: false });
  const inbox: Array<{ type: string; ref: string | null; payload: Record<string, unknown> }> = [];
  ws.on('message', (raw) => inbox.push(JSON.parse(String(raw))));
  await new Promise((res, rej) => {
    ws.once('open', res);
    ws.once('error', rej);
  });
  const send = (type: string, payload: unknown, id = crypto.randomUUID()) => {
    ws.send(JSON.stringify({ type, id, ref: null, ts: new Date().toISOString(), payload }));
    return id;
  };
  const waitFor = async (pred: (m: (typeof inbox)[number]) => boolean) => {
    await expect.poll(() => inbox.find(pred), { timeout: 5000 }).toBeTruthy();
    return inbox.find(pred)!;
  };
  send('AUTH', { token });
  await waitFor((m) => m.type === 'AUTH_OK');
  return { ws, send, waitFor };
}

test('REST: cadastro devolve {id, username}; /me traz stats', async ({ request }) => {
  const u = await createUser(request);
  expect(u.registered).toMatchObject({ username: u.username });
  expect(typeof u.registered.id).toBe('string');
  expect(u.login).toMatchObject({ token_type: 'bearer', user: { username: u.username } });
  const me = await (
    await request.get('/api/me', { headers: { Authorization: `Bearer ${u.token}` } })
  ).json();
  expect(me.stats).toEqual({ wins: 0, losses: 0, draws: 0, points: 0 });
});

test('REST: username repetido dá 409 e corpo malformado dá 422 com detail em lista', async ({
  request,
}) => {
  const u = await createUser(request);
  const dup = await request.post('/api/auth/register', {
    data: { username: u.username, password: 'senha-forte-123' },
  });
  expect(dup.status()).toBe(409);
  expect(typeof (await dup.json()).detail).toBe('string');
  const bad = await request.post('/api/auth/register', { data: { username: 123 } });
  expect(bad.status()).toBe(422);
  expect(Array.isArray((await bad.json()).detail)).toBe(true);
});

test('WS: AUTH repetido responde INVALID_STATE com ref', async ({ request }) => {
  const u = await createUser(request);
  const { ws, send, waitFor } = await openAuthenticated(u.token);
  const id = send('AUTH', { token: u.token });
  const err = await waitFor((m) => m.type === 'ERROR' && m.ref === id);
  expect(err.payload.code).toBe('INVALID_STATE');
  ws.close();
});

test('WS: tipo desconhecido e payload inválido (tipos estritos)', async ({ request }) => {
  const u = await createUser(request);
  const { ws, send, waitFor } = await openAuthenticated(u.token);
  const unknownId = send('JOIN_QUEUE', {});
  expect((await waitFor((m) => m.ref === unknownId)).payload.code).toBe('UNKNOWN_TYPE');
  const strictId = send('MOVE', { match_id: 'm1', cell: '4', seq: 0 }); // cell como texto
  expect((await waitFor((m) => m.ref === strictId)).payload.code).toBe('INVALID_MESSAGE');
  ws.close();
});

test('WS: token inválido fecha com 4401', async () => {
  const ws = new WebSocket(WS_URL, { rejectUnauthorized: false });
  await new Promise((res) => ws.once('open', res));
  ws.send(
    JSON.stringify({
      type: 'AUTH',
      id: 'a1',
      ref: null,
      ts: new Date().toISOString(),
      payload: { token: 'invalido' },
    }),
  );
  const code = await new Promise<number>((res) => ws.once('close', (c) => res(c)));
  expect(code).toBe(4401);
});

test('histórico: devolve `id` (não `_id`) com os campos do contrato', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await b.page.getByRole('button', { name: 'Desistir' }).click();
  await b.page.getByRole('button', { name: 'Desistir' }).last().click();
  await expect(a.page.getByRole('dialog')).toContainText('Você venceu!');

  const token = await a.page.evaluate(() => sessionStorage.getItem('jdv.token'));
  const res = await a.page.request.get('/api/matches/history', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status()).toBe(200);
  const [last] = await res.json();
  expect(last).not.toHaveProperty('_id');
  expect(typeof last.id).toBe('string');
  expect(last).toMatchObject({ reason: 'FORFEIT', winner_id: expect.any(String) });
  expect(typeof last.player_x_id).toBe('string');
  expect(typeof last.player_o_id).toBe('string');
  expect(() => new Date(last.ended_at).toISOString()).not.toThrow();
});

test('TIMEOUT: estourar o tempo do turno dá a vitória ao adversário', async ({
  browser,
  request,
}) => {
  test.skip(!!process.env.E2E_NO_SERVER, 'usa um gancho que só existe no mock');
  await request.post('http://localhost:8000/api/_mock/config', { data: { turn_timeout_s: 2 } });
  try {
    const [a, b] = await twoPlayersInLobby(browser);
    await startMatch(a, b);
    await playMoves(a, b, [0]); // X joga; agora é a vez do O, que não faz nada
    await expect(cell(a.page, 0)).toHaveAccessibleName(/: X$/);
    await expect(a.page.getByRole('dialog')).toContainText('Você venceu!', { timeout: 8000 });
    await expect(a.page.getByRole('dialog')).toContainText('O adversário ficou sem tempo.');
    await expect(b.page.getByRole('dialog')).toContainText('Seu tempo acabou.');
  } finally {
    await request.post('http://localhost:8000/api/_mock/config', { data: { turn_timeout_s: 30 } });
  }
});

test('contador de turno aparece na partida', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await expect(a.page.getByText(/Você tem \d+s para jogar\./)).toBeVisible();
  await expect(b.page.getByText(new RegExp(`${a.name} tem \\d+s para jogar\\.`))).toBeVisible();
});
