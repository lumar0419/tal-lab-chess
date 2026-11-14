"""공개 EPD 전술 모음을 읽어 Stockfish로 정답을 확인하고 희생 여부를 표시해 JSON으로 저장.
사용: build_suite.py <out.json> <이름=epd경로> ...   (Stockfish는 독립 기준으로만 사용)"""
import sys, json, chess, chess.engine
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

out, seen = [], set()
sf = chess.engine.SimpleEngine.popen_uci('/usr/games/stockfish')
sf.configure({'Threads': 1, 'Hash': 64})
for spec in sys.argv[2:]:
    name, path = spec.split('=', 1)
    kept = total = 0
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line or ' bm ' not in line:
            continue
        total += 1
        try:
            board, ops = chess.Board.from_epd(line)
        except Exception as exc:
            print('parse fail', name, line[:60], exc); continue
        bms = ops.get('bm') or []
        if not bms or board.fen() in seen or board.is_game_over():
            continue
        seen.add(board.fen())
        info = sf.analyse(board, chess.engine.Limit(time=1.0), multipv=2)
        best = info[0]['pv'][0]
        if best not in bms:
            continue
        s1 = info[0]['score'].relative.score(mate_score=100000)
        s2 = info[1]['score'].relative.score(mate_score=100000) if len(info) > 1 else -100000
        sv = see(board, best)
        kept += 1
        out.append({'id': str(ops.get('id', f'{name}.{total}')), 'suite': name, 'fen': board.fen(),
                    'bm': [m.uci() for m in bms], 'san': board.san(best), 'see': sv, 'sacrifice': sv <= -100,
                    'check': board.gives_check(best), 'capture': board.is_capture(best),
                    'sf_score': s1, 'sf_gap': s1 - s2, 'mate': info[0]['score'].relative.is_mate()})
    print(f'{name}: {total}개 중 Stockfish 1초 확인 {kept}개', flush=True)
sf.quit()
json.dump(out, open(sys.argv[1], 'w'), indent=0)
from collections import Counter
print(Counter((p['suite'], p['sacrifice']) for p in out))
