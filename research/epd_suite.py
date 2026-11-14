"""공개 EPD 전술 모음을 독립 기준(Stockfish)으로 걸러 JSON으로 만든다.

    python -m research.epd_suite --stockfish /path/to/stockfish --output suite.json wac=wacnew.epd ecm=ecmgcp.epd

각 국면에서 Stockfish 1스레드·1초(기본)의 최선수가 EPD의 bm과 같을 때만 남긴다. 정답 수의
정적 교환 평가(SEE)를 python-chess 비트보드로 따로 계산해 '기물을 내주는 수'(SEE ≤ −100)를 표시한다.
Stockfish와 python-chess는 검증용이며 Tal Lab의 탐색·평가에는 쓰이지 않는다.
"""
import argparse
import json

import chess
import chess.engine

VALUE = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500,
         chess.QUEEN: 900, chess.KING: 20000}


def see(board, move):
    """수를 둔 쪽 기준 정적 교환 평가(cp). board.Board.see와 독립된 구현 (대조용)."""
    to, frm = move.to_square, move.from_square
    occupied = board.occupied
    gains = [0]
    if board.is_en_passant(move):
        gains[0] = 100
        occupied &= ~chess.BB_SQUARES[to + (-8 if board.turn else 8)]
    elif board.piece_type_at(to):
        gains[0] = VALUE[board.piece_type_at(to)]
    piece = board.piece_type_at(frm)
    if move.promotion:
        gains[0] += VALUE[move.promotion] - 100
        piece = move.promotion
    occupied &= ~chess.BB_SQUARES[frm]
    side = not board.turn
    while True:
        attackers = board.attackers_mask(side, to, occupied) & occupied
        if not attackers:
            break
        square = min(chess.scan_forward(attackers), key=lambda s: VALUE[board.piece_type_at(s)])
        kind = board.piece_type_at(square)
        if kind == chess.KING and board.attackers_mask(
                not side, to, occupied & ~chess.BB_SQUARES[square]) & occupied:
            break
        gains.append(VALUE[piece] - gains[-1])
        piece = kind
        occupied &= ~chess.BB_SQUARES[square]
        side = not side
    for index in range(len(gains) - 1, 0, -1):
        gains[index - 1] = -max(-gains[index - 1], gains[index])
    return gains[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--stockfish', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seconds', type=float, default=1.0)
    parser.add_argument('sources', nargs='+', metavar='name=file.epd')
    args = parser.parse_args()
    engine = chess.engine.SimpleEngine.popen_uci(args.stockfish)
    engine.configure({'Threads': 1, 'Hash': 64})
    cases, seen = [], set()
    try:
        for source in args.sources:
            name, path = source.split('=', 1)
            total = kept = 0
            for line in open(path, encoding='utf-8', errors='replace'):
                if ' bm ' not in line:
                    continue
                total += 1
                board, operations = chess.Board.from_epd(line.strip())
                answers = operations.get('bm') or []
                if not answers or board.fen() in seen or board.is_game_over():
                    continue
                seen.add(board.fen())
                lines = engine.analyse(board, chess.engine.Limit(time=args.seconds), multipv=2)
                best = lines[0]['pv'][0]
                if best not in answers:
                    continue
                score = lines[0]['score'].relative.score(mate_score=100000)
                second = lines[1]['score'].relative.score(mate_score=100000) if len(lines) > 1 else -100000
                exchange = see(board, best)
                kept += 1
                cases.append({'id': str(operations.get('id', f'{name}.{total}')), 'suite': name,
                              'fen': board.fen(), 'bm': [move.uci() for move in answers],
                              'san': board.san(best), 'see': exchange, 'sacrifice': exchange <= -100,
                              'check': board.gives_check(best), 'capture': board.is_capture(best),
                              'sf_score': score, 'sf_gap': score - second,
                              'mate': lines[0]['score'].relative.is_mate()})
            print(f'{name}: {total} positions, {kept} confirmed by Stockfish', flush=True)
    finally:
        engine.quit()
    with open(args.output, 'w', encoding='utf-8') as handle:
        json.dump(cases, handle, indent=0)


if __name__ == '__main__':
    main()
