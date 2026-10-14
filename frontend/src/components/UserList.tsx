import { useAuth } from '../context/auth-context'
import { useLobby } from '../context/lobby-context'

export function UserList() {
  const { user, socketStatus } = useAuth()
  const { state, sendInvite } = useLobby()
  const others = state.users.filter((u) => u.username !== user?.username)
  const busy = state.outgoing !== null || state.sending !== null || socketStatus !== 'open'

  if (others.length === 0) {
    return (
      <p className="empty">
        Ninguém mais está online. Peça para um colega entrar ou abra outra aba e entre com outro usuário para testar.
      </p>
    )
  }

  return (
    <ul className="list">
      {others.map((u) => (
        <li key={u.username} className="list__row">
          <span className={`dot dot--${u.status === 'FREE' ? 'free' : 'busy'}`} aria-hidden="true" />
          <span className="list__name">{u.username}</span>
          <span className="muted list__status">{u.status === 'FREE' ? 'Livre' : 'Em partida'}</span>
          <button
            type="button"
            className="btn btn--small"
            disabled={u.status !== 'FREE' || busy}
            onClick={() => sendInvite(u.username)}
          >
            Convidar
          </button>
        </li>
      ))}
    </ul>
  )
}
