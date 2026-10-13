import type { RankingEntry } from '../api'

export function RankingTable({ entries, me, compact }: { entries: RankingEntry[]; me?: string; compact?: boolean }) {
  if (entries.length === 0) {
    return <p className="empty">Ainda não há partidas encerradas. Vença a primeira e apareça aqui.</p>
  }
  return (
    <table className="table">
      <caption className="sr-only">Ranking de jogadores</caption>
      <thead>
        <tr>
          <th scope="col">#</th>
          <th scope="col">Jogador</th>
          <th scope="col" className="num">
            Pts
          </th>
          {!compact && (
            <>
              <th scope="col" className="num" title="Vitórias">
                V
              </th>
              <th scope="col" className="num" title="Empates">
                E
              </th>
              <th scope="col" className="num" title="Derrotas">
                D
              </th>
            </>
          )}
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.username} className={e.username === me ? 'table__me' : undefined}>
            <td>{e.position}</td>
            <td>{e.username}</td>
            <td className="num">{e.points}</td>
            {!compact && (
              <>
                <td className="num">{e.wins}</td>
                <td className="num">{e.draws}</td>
                <td className="num">{e.losses}</td>
              </>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
