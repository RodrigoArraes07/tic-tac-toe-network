import { useSyncExternalStore } from 'react';
import { gameSocket, type SocketStatus } from '../socket';

export function useSocketStatus(): SocketStatus {
  return useSyncExternalStore(gameSocket.subscribeStatus, gameSocket.getStatus);
}
