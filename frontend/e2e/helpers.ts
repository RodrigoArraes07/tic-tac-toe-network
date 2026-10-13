import { expect, type Browser, type Page } from '@playwright/test'

/** username único por execução (o banco real persiste entre execuções). */
export function uniqueName(prefix: string): string {
  return `${prefix}${Date.now().toString(36).slice(-6)}${Math.floor(Math.random() * 36 ** 2).toString(36)}`
}

export async function shot(page: Page, name: string) {
  if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` })
}

/** Cadastra pela UI, entra e espera chegar ao lobby. */
export async function registerAndLogin(page: Page, username: string, password = 'senha-forte-123') {
  await page.goto('/register')
  await page.getByLabel('Usuário').fill(username)
  await page.getByLabel('Senha', { exact: true }).fill(password)
  await page.getByLabel('Repita a senha').fill(password)
  await page.getByRole('button', { name: 'Criar conta' }).click()
  await expect(page.getByText('Conta criada')).toBeVisible()
  await page.getByLabel('Senha', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/lobby/)
  await expect(page.getByText('Conectado')).toBeVisible()
}

/** Só entra (conta já existe). */
export async function login(page: Page, username: string, password = 'senha-forte-123') {
  await page.goto('/login')
  await page.getByLabel('Usuário').fill(username)
  await page.getByLabel('Senha').fill(password)
  await page.getByRole('button', { name: 'Entrar' }).click()
  await expect(page).toHaveURL(/\/lobby/)
  await expect(page.getByText('Conectado')).toBeVisible()
}

export interface Player {
  page: Page
  name: string
}

/** Dois usuários em dois contextos (dois "navegadores") já no lobby. */
export async function twoPlayersInLobby(browser: Browser): Promise<[Player, Player]> {
  const ctxA = await browser.newContext()
  const ctxB = await browser.newContext()
  const a = { page: await ctxA.newPage(), name: uniqueName('ana') }
  const b = { page: await ctxB.newPage(), name: uniqueName('bia') }
  await registerAndLogin(a.page, a.name)
  await registerAndLogin(b.page, b.name)
  return [a, b]
}

/** A convida B e B aceita. Termina com os dois na tela da partida (A = X, B = O). */
export async function startMatch(a: Player, b: Player) {
  await a.page.getByRole('listitem').filter({ hasText: b.name }).getByRole('button', { name: 'Convidar' }).click()
  await expect(b.page.getByRole('dialog')).toContainText(a.name)
  await b.page.getByRole('button', { name: 'Aceitar e jogar' }).click()
  await expect(a.page).toHaveURL(/\/match\//)
  await expect(b.page).toHaveURL(/\/match\//)
}

export const cell = (page: Page, index: number) =>
  page.getByRole('button', { name: new RegExp(`linha ${Math.floor(index / 3) + 1}, coluna ${(index % 3) + 1}`) })

/** Joga em sequência alternando X (a) e O (b). */
export async function playMoves(a: Player, b: Player, cells: number[]) {
  for (let i = 0; i < cells.length; i++) {
    const [mover, other] = i % 2 === 0 ? [a, b] : [b, a]
    await expect(mover.page.getByRole('heading', { name: 'Sua vez' })).toBeVisible()
    await cell(mover.page, cells[i]).click()
    await expect(cell(other.page, cells[i])).toHaveAccessibleName(/: (X|O)$/)
  }
}
