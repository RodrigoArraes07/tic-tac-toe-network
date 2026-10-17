import { useEffect, useState } from 'react';
import { api, type RankingEntry } from '../api';

type RankingState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; entries: RankingEntry[] };

export function useRanking(limit: number) {
  const [state, setState] = useState<RankingState>({ status: 'loading' });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .ranking(limit)
      .then((entries) => {
        if (!cancelled) setState({ status: 'ready', entries });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ status: 'error', message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [limit, nonce]);

  const reload = () => {
    setState({ status: 'loading' });
    setNonce((n) => n + 1);
  };
  return { state, reload };
}
