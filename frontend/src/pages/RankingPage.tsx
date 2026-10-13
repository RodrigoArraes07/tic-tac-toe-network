import { RankingTable } from '../components/RankingTable'
import { useAuth } from '../context/auth-context'
import { useRanking } from '../hooks/useRanking'

export function RankingPage() {
  const { user } = useAuth()
  const { state, reload } = useRanking(50)

  return (
    <section className="sheet">
      <h1 className="sheet__title">Ranking</h1>
      <p className="muted">Vitória vale 3 pontos, empate 1 e derrota 0.</p>
      {state.status === 'loading' && <p className="muted">Carregando ranking…</p>}
      {state.status === 'error' && (
        <p role="alert">
          {state.message}{' '}
          <button type="button" className="link" onClick={reload}>
            Tentar de novo
          </button>
        </p>
      )}
      {state.status === 'ready' && <RankingTable entries={state.entries} me={user?.username} />}
    </section>
  )
}
