"""
perft.py — 수 생성기가 맞는지 검증하는 테스트

perft(depth) = 그 국면에서 depth수 앞까지 나올 수 있는 모든 경우의 수.
체스 프로그래밍 커뮤니티가 여러 국면의 정답 값을 이미 구해 두었기 때문에,
내 엔진이 같은 숫자를 내면 캐슬링·앙파상·승격·핀·체크 처리가 전부 맞다는 강력한 증거가 됩니다.
(정답 출처: chessprogramming.org 'Perft Results')

사용법
  python perft.py                    # 기본 테스트 (몇 초)
  python perft.py --deep             # 한 단계 더 깊게 (1분 안팎)
  python perft.py divide "<FEN>" 3   # 첫 수별 노드 수 → 숫자가 틀릴 때 어느 수가 문제인지 추적
"""

import sys
import time

from board import Board, START_FEN


def perft(b, depth):
    if depth == 0:
        return 1
    moves = b.legal_moves()
    if depth == 1:
        return len(moves)  # 마지막 단계는 수를 두지 않고 세기만 해도 됨
    nodes = 0
    for m in moves:
        b.make_move(m)
        nodes += perft(b, depth - 1)
        b.unmake_move()
    return nodes


def divide(fen, depth):
    b = Board(fen)
    total = 0
    for m in b.legal_moves():
        b.make_move(m)
        n = perft(b, depth - 1)
        b.unmake_move()
        print(f"{m.uci()}: {n}")
        total += n
    print(f"\n총합: {total}")


# (이름, FEN, {깊이: 정답})
TESTS = [
    ("시작 국면", START_FEN,
     {1: 20, 2: 400, 3: 8902, 4: 197281}),
    ("Kiwipete (캐슬링·앙파상·핀 종합)",
     "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
     {1: 48, 2: 2039, 3: 97862, 4: 4085603}),
    ("Position 3 (종반, 앙파상 핀)",
     "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
     {1: 14, 2: 191, 3: 2812, 4: 43238, 5: 674624}),
    ("Position 4 (승격·체크 회피)",
     "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
     {1: 6, 2: 264, 3: 9467, 4: 422333}),
    ("Position 5 (승격으로 체크)",
     "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
     {1: 44, 2: 1486, 3: 62379, 4: 2103487}),
    ("Position 6 (중반)",
     "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
     {1: 46, 2: 2079, 3: 89890, 4: 3894594}),
]

QUICK_LIMIT = 200_000      # 기본 실행: 정답 노드 수가 이 이하인 깊이까지만
DEEP_LIMIT = 5_000_000


def verify_hash(b, depth):
    """트리의 모든 노드에서 '차분 갱신한 해시 == 처음부터 계산한 해시'인지 확인 (3단계 추가)"""
    if b.hash != b.compute_hash():
        raise AssertionError(f"해시 불일치: {b.fen()}")
    if depth == 0:
        return 1
    n = 0
    for m in b.legal_moves():
        b.make_move(m)
        n += verify_hash(b, depth - 1)
        b.unmake_move()
    return n


def run_suite(limit):
    all_ok = True
    start = time.time()
    for name, fen, expected in TESTS:
        b = Board(fen)
        assert b.fen() == fen, f"FEN 왕복 실패: {b.fen()}"
        print(f"\n[{name}]")
        for depth, answer in sorted(expected.items()):
            if answer > limit:
                break
            t0 = time.time()
            got = perft(b, depth)
            ok = got == answer
            all_ok &= ok
            print(f"  depth {depth}: {got:>9,}  (정답 {answer:>9,})  "
                  f"{'OK' if ok else '틀림!'}  {time.time() - t0:5.1f}s")
        assert b.fen() == fen, "make/unmake 후 국면이 원래대로 돌아오지 않음"

    print("\n[Zobrist 해시 검증: 모든 노드에서 차분 갱신 == 처음부터 계산]")
    total = sum(verify_hash(Board(fen), 3) for _, fen, _ in TESTS)
    print(f"  {total:,}개 노드 확인 OK")

    print(f"\n{'모두 통과' if all_ok else '실패한 테스트 있음'}  (총 {time.time() - start:.1f}s)")
    return all_ok


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'divide':
        divide(sys.argv[2], int(sys.argv[3]))
    else:
        ok = run_suite(DEEP_LIMIT if '--deep' in sys.argv else QUICK_LIMIT)
        sys.exit(0 if ok else 1)
