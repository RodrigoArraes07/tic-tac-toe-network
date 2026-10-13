import type { ReactNode } from 'react'
import { Board } from '../components/Board'
import type { Board as BoardType } from '../protocol'

// Partida de exemplo só para ilustrar a tela de entrada.
const SAMPLE: BoardType = ['X', 'O', null, null, 'X', 'O', null, null, 'X']

export function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="entry">
      <div className="entry__art">
        <h1 className="entry__title">Jogo da velha</h1>
        <p className="entry__sub">Dois jogadores, uma partida ao vivo pela rede.</p>
        <Board board={SAMPLE} you={null} canPlay={false} winningLine={[0, 4, 8]} readOnly />
      </div>
      <section className="sheet entry__form" aria-labelledby="entry-title">
        <h2 id="entry-title" className="sheet__title">
          {title}
        </h2>
        {children}
      </section>
    </main>
  )
}
