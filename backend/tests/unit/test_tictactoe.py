import pytest

from app.domain.enums import EndReason, Symbol
from app.domain.tictactoe import WINNING_LINES, apply_move


def test_initial_board_move():
    empty_board = [None] * 9
    new_board, next_turn, result = apply_move(
        board=empty_board, current_turn=Symbol.X, cell=4, player_symbol=Symbol.X
    )
    assert new_board[4] == "X"
    assert next_turn == Symbol.CIRCLE
    assert result is None


def test_invalid_cell_out_of_bounds():
    empty_board = [None] * 9
    with pytest.raises(ValueError, match="INVALID_CELL"):
        apply_move(empty_board, Symbol.X, 9, Symbol.X)


def test_not_your_turn():
    empty_board = [None] * 9
    with pytest.raises(ValueError, match="NOT_YOUR_TURN"):
        apply_move(empty_board, Symbol.X, 0, Symbol.CIRCLE)


def test_cell_occupied():
    board = [None] * 9
    board[0] = "X"
    with pytest.raises(ValueError, match="CELL_OCCUPIED"):
        apply_move(board, Symbol.CIRCLE, 0, Symbol.CIRCLE)


@pytest.mark.parametrize("line", WINNING_LINES)
def test_all_winning_lines_for_x(line):
    # Testa vitória de X em todas as 8 linhas possíveis
    a, b, c = line
    board = [None] * 9
    board[a] = "X"
    board[b] = "X"

    new_board, _, result = apply_move(board, Symbol.X, c, Symbol.X)
    assert result is not None
    assert result["finished"] is True
    assert result["winner"] == "X"
    assert result["reason"] == EndReason.LINE.value
    assert result["winning_line"] == list(line)


def test_draw_scenario():
    # Tabuleiro com 8 posições preenchidas sem vencedor
    # X O X
    # X O O
    # O X .
    board = ["X", "CIRCLE", "X", "X", "CIRCLE", "CIRCLE", "CIRCLE", "X", None]
    new_board, _, result = apply_move(board, Symbol.X, 8, Symbol.X)

    assert result is not None
    assert result["finished"] is True
    assert result["winner"] is None
    assert result["reason"] == EndReason.DRAW.value
    assert result["winning_line"] is None
