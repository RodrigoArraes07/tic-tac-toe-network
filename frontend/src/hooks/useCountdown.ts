import { useEffect, useState } from 'react';

/** Segundos restantes até `expiresAt` (timestamp em ms). 0 quando null. */
export function useCountdown(expiresAt: number | null): number {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (expiresAt === null) return;
    const tick = () => setLeft(Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000)));
    const first = setTimeout(tick, 0);
    const interval = setInterval(tick, 250);
    return () => {
      clearTimeout(first);
      clearInterval(interval);
    };
  }, [expiresAt]);
  return expiresAt === null ? 0 : left;
}
