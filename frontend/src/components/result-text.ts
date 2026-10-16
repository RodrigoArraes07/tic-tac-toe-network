import type { EndReason, MatchResult } from '../protocol'

export function resultTitle(result: MatchResult): string {
  if (result === 'WIN') return 'Você venceu!'
  if (result === 'LOSS') return 'Você perdeu'
  return 'Empate'
}

export function resultDetail(result: MatchResult, reason: EndReason): string {
  switch (reason) {
    case 'LINE':
      return result === 'WIN' ? 'Você fechou três em linha.' : 'Seu adversário fechou três em linha.'
    case 'DRAW':
      return 'O tabuleiro encheu sem ninguém fechar três em linha.'
    case 'FORFEIT':
      return result === 'WIN' ? 'Seu adversário desistiu.' : 'Você desistiu da partida.'
    case 'TIMEOUT':
      return result === 'WIN' ? 'Seu adversário não jogou a tempo.' : 'Seu tempo para jogar acabou.'
    case 'DISCONNECT':
      return result === 'WIN' ? 'Seu adversário perdeu a conexão.' : 'Você ficou sem conexão por tempo demais.'
  }
}
