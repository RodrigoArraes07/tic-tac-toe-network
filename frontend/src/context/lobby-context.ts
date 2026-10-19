import { createContext, useContext } from 'react';
import type { LobbyState } from './lobby-reducer';

export interface LobbyContextValue {
  state: LobbyState;
  sendInvite: (username: string) => void;
  cancelInvite: () => void;
  respondInvite: (matchId: string, accept: boolean) => void;
}

export const LobbyContext = createContext<LobbyContextValue | null>(null);

export function useLobby(): LobbyContextValue {
  const value = useContext(LobbyContext);
  if (!value) throw new Error('useLobby fora do LobbyProvider');
  return value;
}
