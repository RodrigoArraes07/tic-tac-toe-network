import { createContext, useContext } from 'react';
import type { MatchState } from './match-reducer';

export interface MatchContextValue {
  state: MatchState;
  playMove: (cell: number) => void;
  forfeit: () => void;
  syncMatch: (matchId: string) => void;
  /** Limpa a partida local e volta ao lobby. */
  leaveMatch: () => void;
}

export const MatchContext = createContext<MatchContextValue | null>(null);

export function useMatch(): MatchContextValue {
  const value = useContext(MatchContext);
  if (!value) throw new Error('useMatch fora do MatchProvider');
  return value;
}
