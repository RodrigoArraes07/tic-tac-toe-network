import type { SocketStatus } from '../socket';

const LABELS: Record<SocketStatus, { text: string; tone: 'ok' | 'wait' | 'bad' }> = {
  idle: { text: 'Offline', tone: 'bad' },
  connecting: { text: 'Conectando…', tone: 'wait' },
  reconnecting: { text: 'Reconectando…', tone: 'wait' },
  open: { text: 'Conectado', tone: 'ok' },
  replaced: { text: 'Sessão em outra aba', tone: 'bad' },
  closed: { text: 'Desconectado', tone: 'bad' },
};

export function ConnectionBadge({ status }: { status: SocketStatus }) {
  const { text, tone } = LABELS[status];
  return (
    <span className="conn" role="status">
      <span className={`conn__dot conn__dot--${tone}`} aria-hidden="true" />
      {text}
    </span>
  );
}
