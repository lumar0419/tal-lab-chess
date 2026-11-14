"""board.see()를 python-chess 비트보드로 따로 구현한 SEE와 대조. 사용: see_check.py <엔진폴더>"""
import sys, random, importlib.util
sys.path.insert(0, sys.argv[1])
import chess
from board import Board
spec = importlib.util.spec_from_file_location('bs', '/home/claude/v087/scripts/see_ref.py'); ref = importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
rng = random.Random(5); n = bad = caps = neg = 0
for g in range(400):
    pb = chess.Board()
    for _ in range(120):
        ms = list(pb.legal_moves)
        if not ms: break
        caps_ = [m for m in ms if pb.is_capture(m)]
        pb.push(rng.choice(caps_) if caps_ and rng.random() < .3 else rng.choice(ms))
        if pb.is_game_over(): break
        b = Board(pb.fen())
        snap = b.snapshot()
        for m in b.legal_moves():
            mine = b.see(m)
            want = ref.see(pb, chess.Move.from_uci(m.uci()))
            n += 1; caps += pb.is_capture(chess.Move.from_uci(m.uci())); neg += want < 0
            if mine != want:
                bad += 1
                if bad <= 5: print('불일치', pb.fen(), m.uci(), mine, want)
        assert b.snapshot() == snap, 'see()가 보드를 바꿈'
print(f'수 {n}개 (캡처 {caps}, SEE 음수 {neg}): 불일치 {bad}')
