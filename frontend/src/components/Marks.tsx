import type { PlayerSymbol } from '../protocol';

/** X e O desenhados como traços (a animação de "riscar" está no index.css). */
export function Mark({ symbol, animate = true }: { symbol: PlayerSymbol; animate?: boolean }) {
  const cls = animate ? 'mark-path mark-path--draw' : 'mark-path';
  if (symbol === 'X') {
    return (
      <svg viewBox="0 0 100 100" className="mark mark--x" aria-hidden="true">
        <path d="M24 24 L76 76" pathLength={1} className={cls} />
        <path
          d="M76 24 L24 76"
          pathLength={1}
          className={cls}
          style={{ animationDelay: '0.16s' }}
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 100 100" className="mark mark--o" aria-hidden="true">
      <circle cx="50" cy="50" r="28" transform="rotate(-90 50 50)" pathLength={1} className={cls} />
    </svg>
  );
}
