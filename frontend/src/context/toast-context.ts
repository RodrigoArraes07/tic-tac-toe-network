import { createContext, useContext } from 'react';

export type ToastKind = 'info' | 'success' | 'error';

export interface ToastContextValue {
  push: (message: string, kind?: ToastKind) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error('useToast fora do ToastProvider');
  return value;
}
