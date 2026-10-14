import { OutgoingInvite } from '../components/OutgoingInvite'
import { RankingPanel } from '../components/RankingPanel'
import { UserList } from '../components/UserList'

export function LobbyPage() {
  return (
    <div className="lobby">
      <div className="lobby__main">
        <OutgoingInvite />
        <section className="sheet" aria-labelledby="online-title">
          <h1 id="online-title" className="sheet__title">
            Jogadores online
          </h1>
          <UserList />
        </section>
      </div>
      <RankingPanel />
    </div>
  )
}
