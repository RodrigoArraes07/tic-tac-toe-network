import { expect, test } from '@playwright/test';
import {
  cell,
  login,
  playMoves,
  registerAndLogin,
  shot,
  startMatch,
  twoPlayersInLobby,
  uniqueName,
} from './helpers';

const STATE_ERROR_MESSAGE = 'Ação incompatível com o estado da partida.';
const TURN_SECONDS = 30;
const AWAY_MS = 4000;

test('T06: dois usuários se veem online', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await expect(a.page.getByRole('listitem').filter({ hasText: b.name })).toContainText('Livre');
  await expect(b.page.getByRole('listitem').filter({ hasText: a.name })).toContainText('Livre');
  await shot(a.page, '1-lobby');
});

test('T08: convite recusado volta os dois ao estado livre', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await a.page
    .getByRole('listitem')
    .filter({ hasText: b.name })
    .getByRole('button', { name: 'Convidar' })
    .click();
  await expect(a.page.getByText(/Convite enviado para/)).toBeVisible();
  await shot(a.page, '2-convite-enviado');
  await expect(b.page.getByRole('dialog')).toBeVisible();
  await shot(b.page, '3-convite-recebido');
  await b.page.getByRole('button', { name: 'Recusar' }).click();
  await expect(a.page.getByText(`${b.name} recusou o convite.`)).toBeVisible();
  await expect(a.page.getByText(/Convite enviado para/)).toHaveCount(0);
  await expect(
    a.page
      .getByRole('listitem')
      .filter({ hasText: b.name })
      .getByRole('button', { name: 'Convidar' }),
  ).toBeEnabled();
});

test('T08: convidante cancela', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await a.page
    .getByRole('listitem')
    .filter({ hasText: b.name })
    .getByRole('button', { name: 'Convidar' })
    .click();
  await expect(b.page.getByRole('dialog')).toBeVisible();
  await a.page.getByRole('button', { name: 'Cancelar convite' }).click();
  await expect(b.page.getByRole('dialog')).toBeHidden();
});

test('T07/T14/T21: partida até a vitória de X e ranking atualizado', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await expect(a.page.getByText(/Você joga com/)).toContainText('X');
  await expect(b.page.getByText(/Você joga com/)).toContainText('O');
  await expect(b.page.getByRole('heading', { name: `Vez de ${a.name}` })).toBeVisible();
  await shot(a.page, '4-partida-inicio');

  await playMoves(a, b, [0, 3, 1, 4]);
  await shot(a.page, '5-partida-meio');
  await cell(a.page, 2).click();

  await expect(a.page.getByRole('dialog')).toContainText('Você venceu!');
  await expect(b.page.getByRole('dialog')).toContainText('Você perdeu');
  await shot(a.page, '6-resultado-vitoria');
  await shot(b.page, '7-resultado-derrota');

  await a.page.getByRole('button', { name: 'Ver tabuleiro' }).click();
  await shot(a.page, '8-tabuleiro-final');
  await a.page.getByRole('button', { name: 'Voltar ao lobby' }).click();
  await b.page.getByRole('dialog').getByRole('button', { name: 'Voltar ao lobby' }).click();
  await expect(a.page).toHaveURL(/\/lobby/);

  await a.page.getByRole('link', { name: 'Ranking' }).click();
  const row = a.page.getByRole('row').filter({ hasText: a.name });
  await expect(row).toContainText('3');
  await shot(a.page, '9-ranking');
});

test('T15: empate', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await playMoves(a, b, [0, 1, 2, 4, 3, 5, 7, 6, 8]);
  await expect(a.page.getByRole('dialog')).toContainText('Empate');
  await expect(b.page.getByRole('dialog')).toContainText('Empate');
});

test('T16: desistência dá a vitória ao adversário', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await b.page.getByRole('button', { name: 'Desistir' }).click();
  await expect(b.page.getByRole('dialog')).toContainText('Desistir da partida?');
  await shot(b.page, '10-confirmar-desistencia');
  await b.page.getByRole('button', { name: 'Desistir' }).last().click();
  await expect(a.page.getByRole('dialog')).toContainText('Você venceu!');
  await expect(a.page.getByRole('dialog')).toContainText('Seu adversário desistiu.');
  await expect(b.page.getByRole('dialog')).toContainText('Você desistiu da partida.');
});

test('voltar ao lobby depois do fim não mostra erro do servidor', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await b.page.getByRole('button', { name: 'Desistir' }).click();
  await b.page.getByRole('button', { name: 'Desistir' }).last().click();
  await expect(a.page.getByRole('dialog')).toContainText('Você venceu!');

  for (const player of [a, b]) {
    await player.page.getByRole('dialog').getByRole('button', { name: 'Voltar ao lobby' }).click();
    await expect(player.page).toHaveURL(/\/lobby/);
  }
  // Tempo para um MATCH_SYNC indevido ir e voltar. A contagem é pontual: o toast some
  // em 4,5 s, e uma asserção com nova tentativa acabaria passando depois que ele sumisse.
  await a.page.waitForTimeout(1000);

  for (const player of [a, b]) {
    expect(await player.page.getByText(STATE_ERROR_MESSAGE).count()).toBe(0);
  }
});

test('reconexão: contador oculto na janela e reiniciado na volta do adversário', async ({
  browser,
}) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  const matchUrl = a.page.url();
  const timer = b.page.getByText(new RegExp(`${a.name} tem \\d+s para jogar`));
  await expect(timer).toBeVisible();

  // A sai da página (o socket fecha) e volta depois de alguns segundos.
  await a.page.goto('about:blank');
  await expect(b.page.getByRole('status').filter({ hasText: 'perdeu a conexão' })).toBeVisible();
  await expect(timer).toBeHidden();
  await b.page.waitForTimeout(AWAY_MS);
  await a.page.goto(matchUrl);

  await expect(b.page.getByRole('status').filter({ hasText: 'perdeu a conexão' })).toBeHidden();
  await expect(timer).toBeVisible();
  const secondsLeft = Number((await timer.textContent())?.match(/(\d+)s/)?.[1]);
  expect(secondsLeft).toBeGreaterThanOrEqual(TURN_SECONDS - 2);
});

test('T11/T10: não dá para jogar fora do turno nem em casa ocupada', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await expect(cell(b.page, 4)).toBeDisabled(); // vez do X
  await cell(a.page, 4).click();
  await expect(cell(a.page, 4)).toBeDisabled(); // ocupada
  await expect(cell(b.page, 4)).toBeDisabled(); // ocupada (vista pelo adversário)
  await expect(cell(b.page, 0)).toBeEnabled(); // agora é a vez do O
});

test('T18: recarregar a página no meio da partida retoma o jogo', async ({ browser }) => {
  const [a, b] = await twoPlayersInLobby(browser);
  await startMatch(a, b);
  await playMoves(a, b, [0, 4]);
  await a.page.reload();
  await expect(a.page).toHaveURL(/\/match\//);
  await expect(cell(a.page, 0)).toHaveAccessibleName(/: X$/);
  await expect(cell(a.page, 4)).toHaveAccessibleName(/: O$/);
  await expect(a.page.getByRole('heading', { name: 'Sua vez' })).toBeVisible();
  await cell(a.page, 2).click();
  await expect(cell(b.page, 2)).toHaveAccessibleName(/: X$/);
});

test('T23: mesma conta em segunda aba derruba a primeira conexão', async ({ browser }) => {
  const ctx = await browser.newContext();
  const first = await ctx.newPage();
  const name = uniqueName('tab');
  await registerAndLogin(first, name);
  const second = await ctx.newPage();
  await login(second, name);
  await expect(first.getByRole('alert')).toContainText('aberta em outra aba');
  await shot(first, '11-sessao-em-outra-aba');
  await first.getByRole('button', { name: 'Usar esta aba' }).click();
  await expect(first.getByText('Conectado')).toBeVisible();
  await expect(second.getByRole('alert')).toContainText('aberta em outra aba');
});

test('login com senha errada mostra erro genérico', async ({ page }) => {
  await page.goto('/login');
  await shot(page, '0-login');
  await page.getByLabel('Usuário').fill('ninguem');
  await page.getByLabel('Senha').fill('senha-errada-1');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByRole('alert')).toContainText('Usuário ou senha inválidos');
});

test('rota protegida sem login redireciona para /login', async ({ page }) => {
  await page.goto('/lobby');
  await expect(page).toHaveURL(/\/login/);
});

test('cadastro valida os campos antes de enviar', async ({ page }) => {
  await page.goto('/register');
  await page.getByLabel('Usuário').fill('a!');
  await page.getByLabel('Senha', { exact: true }).fill('curta');
  await page.getByLabel('Repita a senha').fill('outra');
  await page.getByRole('button', { name: 'Criar conta' }).click();
  await expect(page.getByText('Use de 3 a 20 caracteres.')).toBeVisible();
  await expect(page.getByText('A senha precisa de pelo menos 8 caracteres.')).toBeVisible();
  await expect(page.getByText('As senhas não são iguais.')).toBeVisible();
});
