from typing import Any

from app.domain.enums import EndReason, Symbol

# As 8 linhas vencedoras: 3 horizontais, 3 verticais, 2 diagonais
WINNING_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),  # Linhas
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),  # Colunas
    (0, 4, 8),
    (2, 4, 6),  # Diagonais
)


def check_winner(board: list[str | None]) -> tuple[Symbol, tuple[int, int, int]] | None:
    """
    Verifica se há um vencedor no tabuleiro.
    Retorna uma tupla (símbolo_vencedor, linha_vencedora) ou None.
    """
    for line in WINNING_LINES:
        a, b, c = line
        if board[a] and board[a] == board[b] == board[c]:
            return Symbol(board[a]), line
    return None


def is_board_full(board: list[str | None]) -> bool:
    """Verifica se todas as 9 posições estão ocupadas."""
    return all(cell is not None for cell in board)


def apply_move(
    board: list[str | None], current_turn: Symbol, cell: int, player_symbol: Symbol
) -> tuple[list[str | None], Symbol, dict[str, Any] | None]:
    """
    Aplica uma jogada no tabuleiro.

    Validações realizadas:
    - Posição válida (0 a 8)
    - Turno do jogador correto
    - Casa desocupada

    Retorna:
    (novo_tabuleiro, proximo_turno, resultado_se_final)
    """
    if cell < 0 or cell > 8:
        raise ValueError("INVALID_CELL")

    if player_symbol != current_turn:
        raise ValueError("NOT_YOUR_TURN")

    if board[cell] is not None:
        raise ValueError("CELL_OCCUPIED")

    # Copia o tabuleiro e aplica a jogada
    new_board = list(board)
    new_board[cell] = player_symbol.value

    # 1. Checa vitória
    win_info = check_winner(new_board)
    if win_info:
        winner_symbol, winning_line = win_info
        result = {
            "finished": True,
            "winner": winner_symbol.value,
            "reason": EndReason.LINE.value,
            "winning_line": list(winning_line),
        }
        return new_board, current_turn, result

    # 2. Checa empate
    if is_board_full(new_board):
        result = {
            "finished": True,
            "winner": None,
            "reason": EndReason.DRAW.value,
            "winning_line": None,
        }
        return new_board, current_turn, result

    # 3. Partida continua: alterna o turno
    next_turn = Symbol.CIRCLE if current_turn == Symbol.X else Symbol.X
    return new_board, next_turn, None
