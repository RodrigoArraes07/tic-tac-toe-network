import type { EndReason } from './protocol';

// REST (seção 7.1). URLs relativas: o proxy do Vite (dev) e o Nginx (prod)
// encaminham /api ao backend.

export interface UserStats {
  wins: number;
  draws: number;
  losses: number;
  points: number;
}

export interface User {
  id: string;
  username: string;
  stats?: UserStats;
}

export interface RankingEntry {
  position: number;
  username: string;
  points: number;
  wins: number;
  draws: number;
  losses: number;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

/** Item de GET /api/matches/history (ids em texto; o histórico usa `id`, não `_id`). */
export interface MatchHistoryEntry {
  id: string;
  player_x_id: string;
  player_o_id: string;
  winner_id: string | null;
  reason: EndReason;
  ended_at: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const TOKEN_KEY = 'jdv.token';

/** Token em sessionStorage (por aba) — seção 12.1. */
export const tokenStore = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: () => void = () => {};
/** Chamado quando uma rota autenticada responde 401 (token expirado). */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

/** O back-end responde {"detail": "..."} em português; no 422 de corpo malformado, `detail` é uma lista. */
async function readErrorMessage(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const { detail } = body as { detail: unknown };
      if (typeof detail === 'string' && detail.trim()) return detail;
    }
  } catch {
    // corpo vazio ou não-JSON: cai na mensagem genérica
  }
  if (res.status === 409) return 'Esse username já está em uso.';
  if (res.status === 429) return 'Muitas tentativas. Aguarde um minuto e tente de novo.';
  if (res.status === 422) return 'Dados inválidos. Confira os campos e tente de novo.';
  if (res.status === 401) return 'Usuário ou senha inválidos.';
  return 'Algo deu errado no servidor. Tente de novo em instantes.';
}

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  const token = options.auth ? tokenStore.get() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'Não foi possível falar com o servidor. Verifique sua conexão.');
  }

  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized();
    throw new ApiError(res.status, await readErrorMessage(res));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  register: (username: string, password: string) =>
    request<{ id: string; username: string }>('/auth/register', {
      method: 'POST',
      body: { username, password },
    }),
  login: (username: string, password: string) =>
    request<LoginResponse>('/auth/login', { method: 'POST', body: { username, password } }),
  me: () => request<User>('/me', { auth: true }),
  history: () => request<MatchHistoryEntry[]>('/matches/history', { auth: true }),
  ranking: (limit = 20) => request<RankingEntry[]>(`/ranking?limit=${limit}`, { auth: true }),
};
