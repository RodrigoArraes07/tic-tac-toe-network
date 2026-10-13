import { useAuth } from '../context/auth-context'
import { useRanking } from '../hooks/useRanking'
import { RankingTable } from './RankingTable'

export function RankingPanel() {
  const { user } = useAuth()
  const { state, reload } = useRanking(10)

  return (
    <section className="sheet" aria-labelledby="rk-title">
      <h2 id="rk-title" className="sheet__title">
        Top 10
      </h2>
      {state.status === 'loading' && <p className="muted">Carregando ranking…</p>}
      {state.status === 'error' && (
        <p role="alert">
          {state.message}{' '}
          <button type="button" className="link" onClick={reload}>
            Tentar de novo
          </button>
        </p>
      )}
      {state.status === 'ready' && <RankingTable entries={state.entries} me={user?.username} compact />}
    </section>
  )
}
