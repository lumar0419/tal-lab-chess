import chess
VAL = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}

def see(board, move):
    """정적 교환 평가 (python-chess, x-ray 포함). 수를 둔 쪽 기준 cp."""
    to, frm = move.to_square, move.from_square
    occ = board.occupied
    gain = [0]
    if board.is_en_passant(move):
        gain[0] = 100
        occ &= ~chess.BB_SQUARES[to + (-8 if board.turn else 8)]
    elif board.piece_type_at(to):
        gain[0] = VAL[board.piece_type_at(to)]
    piece = board.piece_type_at(frm)
    if move.promotion:
        gain[0] += VAL[move.promotion] - 100
        piece = move.promotion
    occ &= ~chess.BB_SQUARES[frm]
    side = not board.turn
    d = 0
    while True:
        att = board.attackers_mask(side, to, occ) & occ
        if not att:
            break
        best_sq, best_pt = None, None
        for sq in chess.scan_forward(att):
            pt = board.piece_type_at(sq)
            if best_pt is None or VAL[pt] < VAL[best_pt]:
                best_sq, best_pt = sq, pt
        d += 1
        gain.append(VAL[piece] - gain[d - 1])
        if best_pt == chess.KING and board.attackers_mask(not side, to, occ & ~chess.BB_SQUARES[best_sq]) & occ:
            gain.pop(); d -= 1
            break
        piece = best_pt
        occ &= ~chess.BB_SQUARES[best_sq]
        side = not side
    while d > 0:
        gain[d - 1] = -max(-gain[d - 1], gain[d])
        d -= 1
    return gain[0]

