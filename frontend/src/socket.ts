// Dono único da conexão WebSocket (seção 13.3). Vive FORA dos componentes
// para o StrictMode não abrir duas conexões (o servidor fecharia a 1ª com 4001).

import type {
  ClientPayloads,
  ClientType,
  ServerMessage,
  ServerMessageOf,
  ServerType,
} from './protocol';
import { uuid } from './util';

export type SocketStatus =
  | 'idle' // sem sessão
  | 'connecting' // primeira tentativa
  | 'reconnecting' // caiu e está tentando de novo (backoff)
  | 'open' // AUTH_OK recebido
  | 'replaced' // 4001: a conta abriu em outra aba
  | 'closed'; // 4401: token inválido/expirado

type AnyHandler = (msg: ServerMessage) => void;

const MAX_BACKOFF_MS = 30_000;
const ACTIVE: SocketStatus[] = ['connecting', 'reconnecting', 'open'];

export class GameSocket {
  private ws: WebSocket | null = null;
  private token: string | null = null;
  private status: SocketStatus = 'idle';
  private retries = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private handlers = new Map<string, Set<AnyHandler>>();
  private statusListeners = new Set<() => void>();
  private authFailedListeners = new Set<() => void>();

  // Arrow functions: referência estável para useSyncExternalStore.
  getStatus = (): SocketStatus => this.status;

  subscribeStatus = (listener: () => void): (() => void) => {
    this.statusListeners.add(listener);
    return () => {
      this.statusListeners.delete(listener);
    };
  };

  /** Avisa quando o servidor recusa o token (close code 4401). */
  onAuthFailed(listener: () => void): () => void {
    this.authFailedListeners.add(listener);
    return () => {
      this.authFailedListeners.delete(listener);
    };
  }

  /** Assina mensagens de um tipo. Retorna a função de cancelamento. */
  subscribe<K extends ServerType>(type: K, handler: (msg: ServerMessageOf<K>) => void) {
    const set = this.handlers.get(type) ?? new Set<AnyHandler>();
    this.handlers.set(type, set);
    const fn = handler as unknown as AnyHandler;
    set.add(fn);
    return () => {
      set.delete(fn);
    };
  }

  /** Idempotente: chamar duas vezes com o mesmo token não abre outra conexão. */
  connect(token: string) {
    if (this.token === token && ACTIVE.includes(this.status)) return;
    this.clearTimer();
    this.detach();
    this.token = token;
    this.retries = 0;
    this.open('connecting');
  }

  /** Logout: fecha de forma limpa (1000) e não reconecta. */
  disconnect() {
    this.clearTimer();
    this.token = null;
    this.detach();
    this.setStatus('idle');
  }

  /** Após 4001: o usuário escolheu usar esta aba (derruba a outra). */
  resume() {
    if (this.status !== 'replaced' || !this.token) return;
    this.retries = 0;
    this.open('connecting');
  }

  /** Retorna o id da mensagem (para casar com `ref` de um ERROR) ou null se offline. */
  send<K extends ClientType>(type: K, payload: ClientPayloads[K]): string | null {
    if (this.status !== 'open') return null;
    return this.sendRaw(type, payload);
  }

  private sendRaw(type: ClientType, payload: unknown): string | null {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return null;
    const id = uuid();
    this.ws.send(JSON.stringify({ type, id, ref: null, ts: new Date().toISOString(), payload }));
    return id;
  }

  private open(status: SocketStatus) {
    this.setStatus(status);
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${scheme}://${location.host}/ws`);
    this.ws = ws;
    // O navegador não permite cabeçalhos no WebSocket: o token vai na 1ª mensagem.
    ws.onopen = () => {
      if (this.token) this.sendRaw('AUTH', { token: this.token });
    };
    ws.onmessage = (ev) => this.handleMessage(ev.data);
    ws.onclose = (ev) => {
      if (this.ws !== ws) return; // conexão antiga já descartada
      this.ws = null;
      this.handleClose(ev.code);
    };
    ws.onerror = () => {
      // o onclose sempre vem em seguida; a lógica fica lá
    };
  }

  private handleMessage(data: unknown) {
    let msg: ServerMessage;
    try {
      const parsed: unknown = JSON.parse(String(data));
      if (
        !parsed ||
        typeof parsed !== 'object' ||
        typeof (parsed as { type?: unknown }).type !== 'string'
      ) {
        throw new Error('envelope inválido');
      }
      msg = parsed as ServerMessage;
    } catch {
      console.warn('[socket] mensagem ignorada (não é um envelope válido)', data);
      return;
    }
    if (msg.type === 'AUTH_OK') {
      this.retries = 0;
      this.setStatus('open');
    }
    for (const handler of this.handlers.get(msg.type) ?? []) {
      try {
        handler(msg);
      } catch (err) {
        console.error('[socket] erro no handler de', msg.type, err);
      }
    }
  }

  private handleClose(code: number) {
    if (code === 4401) {
      this.token = null;
      this.setStatus('closed');
      this.authFailedListeners.forEach((l) => l());
      return;
    }
    if (code === 4001) {
      this.setStatus('replaced'); // não reconectar (seção 7.5)
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect() {
    this.setStatus('reconnecting');
    const delay = Math.min(1000 * 2 ** this.retries, MAX_BACKOFF_MS); // 1, 2, 4, 8... 30 s
    this.retries += 1;
    this.timer = setTimeout(() => {
      this.timer = null;
      if (this.token) this.open('reconnecting');
    }, delay);
  }

  private detach() {
    const ws = this.ws;
    if (!ws) return;
    this.ws = null;
    ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
    ws.close(1000);
  }

  private clearTimer() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private setStatus(next: SocketStatus) {
    if (this.status === next) return;
    this.status = next;
    this.statusListeners.forEach((l) => l());
  }
}

export const gameSocket = new GameSocket();
