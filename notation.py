"""SAN notation shared by server and browser Python runtimes."""
from board import EMPTY, file_of, rank_of, sq_name

def san_for_move(board, move):
    """SAN for a *legal* move, including disambiguation, en passant, promo, +/#."""
    piece = board.board[move.frm]
    kind = piece.upper()
    capture = board.board[move.to] != EMPTY or (kind == 'P' and move.to == board.ep)
    if kind == 'K' and abs(move.to - move.frm) == 2:
        label = 'O-O' if move.to > move.frm else 'O-O-O'
    else:
        prefix = '' if kind == 'P' else kind
        if kind == 'P' and capture:
            prefix = 'abcdefgh'[file_of(move.frm)]
        elif kind != 'P':
            others = [candidate for candidate in board.legal_moves()
                      if candidate != move and candidate.to == move.to
                      and board.board[candidate.frm] == piece]
            if others:
                same_file = any(file_of(c.frm) == file_of(move.frm) for c in others)
                same_rank = any(rank_of(c.frm) == rank_of(move.frm) for c in others)
                if not same_file:
                    prefix += 'abcdefgh'[file_of(move.frm)]
                elif not same_rank:
                    prefix += str(rank_of(move.frm) + 1)
                else:
                    prefix += sq_name(move.frm)
        label = prefix + ('x' if capture else '') + sq_name(move.to)
        if move.promo:
            label += '=' + move.promo.upper()
    board.make_move(move)
    try:
        if board.in_check():
            label += '#' if not board.has_legal_move(in_check=True) else '+'
    finally:
        board.unmake_move()
    return label
