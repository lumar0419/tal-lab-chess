"""Compare Tal Lab's exchange score with independent legal python-chess recaptures."""
import argparse
import json
import random
from pathlib import Path

import chess

from board import Board

VALUES = dict(zip(range(chess.PAWN, chess.KING + 1), (100, 320, 330, 500, 900, 20000)))


def exchange(board, move):
    victim = chess.PAWN if board.is_en_passant(move) else board.piece_type_at(move.to_square)
    gain = VALUES.get(victim, 0) + (VALUES[move.promotion] - 100 if move.promotion else 0)
    target = chess.BB_SQUARES[move.to_square]
    board.push(move)
    try:
        replies = board.generate_legal_captures(to_mask=target)
        return gain - max(0, max((exchange(board, reply) for reply in replies), default=0))
    finally:
        board.pop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--games', type=int, default=400)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(5)
    report = dict(games=args.games, seed=5, positions=0, moves=0, captures=0,
                  promotions=0, en_passant=0, mismatches=[], estimate_mismatches=0,
                  estimate_negative_legal_nonnegative=0)
    for _ in range(args.games):
        oracle = chess.Board()
        for _ in range(120):
            moves = list(oracle.legal_moves)
            if not moves:
                break
            captures = [move for move in moves if oracle.is_capture(move)]
            oracle.push(rng.choice(captures) if captures and rng.random() < .3 else rng.choice(moves))
            if oracle.is_game_over():
                break
            board = Board(oracle.fen())
            snapshot = board.snapshot()
            report['positions'] += 1
            for move in board.legal_moves():
                reference_move = chess.Move.from_uci(move.uci())
                expected = exchange(oracle, reference_move)
                actual = board.see(move)
                estimated = board.see_estimate(move)
                report['moves'] += 1
                report['captures'] += oracle.is_capture(reference_move)
                report['promotions'] += bool(move.promo)
                report['en_passant'] += oracle.is_en_passant(reference_move)
                report['estimate_mismatches'] += estimated != expected
                report['estimate_negative_legal_nonnegative'] += estimated < 0 <= expected
                if actual != expected:
                    report['mismatches'].append(dict(fen=board.fen(), move=move.uci(), actual=actual,
                                                     expected=expected))
            assert board.snapshot() == snapshot
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    if report['mismatches']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
