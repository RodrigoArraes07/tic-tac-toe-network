import type { Board as BoardType, PlayerSymbol } from '../protocol';
import styles from './Board.module.css';
import { Mark } from './Marks';

interface BoardProps {
  board: BoardType;
  /** Meu símbolo (usado na prévia ao passar o mouse). */
  you: PlayerSymbol | null;
  /** É a minha vez e a partida está em andamento. */
  canPlay: boolean;
  pendingCell?: number | null;
  winningLine?: number[] | null;
  onPlay?: (cell: number) => void;
  /** Só exibe (ex.: ilustração da tela de login). */
  readOnly?: boolean;
}

const center = (cell: number) => ({ x: (cell % 3) * 100 + 50, y: Math.floor(cell / 3) * 100 + 50 });

function describe(value: BoardType[number], index: number) {
  const position = `linha ${Math.floor(index / 3) + 1}, coluna ${(index % 3) + 1}`;
  return `${position}: ${value ?? 'vazia'}`;
}

export function Board({
  board,
  you,
  canPlay,
  pendingCell = null,
  winningLine,
  onPlay,
  readOnly,
}: BoardProps) {
  let winLine: { x1: number; y1: number; x2: number; y2: number; symbol: PlayerSymbol } | null =
    null;
  if (winningLine && winningLine.length >= 2) {
    const a = center(winningLine[0]);
    const b = center(winningLine[winningLine.length - 1]);
    const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const dx = ((b.x - a.x) / len) * 24;
    const dy = ((b.y - a.y) / len) * 24;
    const symbol = board[winningLine[0]];
    if (symbol) winLine = { x1: a.x - dx, y1: a.y - dy, x2: b.x + dx, y2: b.y + dy, symbol };
  }

  return (
    <div className={styles.board} role="group" aria-label="Tabuleiro">
      <svg className={styles.grid} viewBox="0 0 300 300" aria-hidden="true">
        <path d="M100 10 V290 M200 10 V290 M10 100 H290 M10 200 H290" />
      </svg>

      <div className={styles.cells}>
        {board.map((value, i) => {
          const playable = !readOnly && canPlay && value === null && pendingCell === null;
          const showPending = pendingCell === i;
          return (
            <button
              key={i}
              type="button"
              className={styles.cell}
              disabled={!playable}
              tabIndex={readOnly ? -1 : undefined}
              aria-label={describe(value, i)}
              onClick={() => onPlay?.(i)}
            >
              {value && <Mark symbol={value} animate />}
              {showPending && you && (
                <span className={styles.pending}>
                  <Mark symbol={you} animate={false} />
                </span>
              )}
              {playable && you && (
                <span className={styles.ghost}>
                  <Mark symbol={you} animate={false} />
                </span>
              )}
            </button>
          );
        })}
      </div>

      {winLine && (
        <svg className={styles.win} viewBox="0 0 300 300" aria-hidden="true">
          <line
            x1={winLine.x1}
            y1={winLine.y1}
            x2={winLine.x2}
            y2={winLine.y2}
            pathLength={1}
            className={winLine.symbol === 'X' ? styles.winX : styles.winO}
          />
        </svg>
      )}
    </div>
  );
}
