"""TacticalChecks 옵션 ON/OFF 비교: 동일한 단일 엔진 설정만 변경.

python bench_tactics.py
결과는 로컬 소규모 벤치마크. 실전 Elo 또는 장기 승률을 대체하지 않는다.
"""
import statistics
import time
from board import Board, START_FEN
from search import Searcher

CASES = [
    ('start', START_FEN),
    ('Italian', 'r1bqk2r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4'),
    ('Kiwipete', 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1'),
    ('queen-bait horizon', '7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1'),
    ('quiet rook mate', '7k/8/6K1/8/8/8/8/R7 w - - 0 1'),
]


def run_case(fen, enabled, depth):
    s = Searcher(tt_size=16_000)
    s.qsearch_quiet_checks = enabled
    b = Board(fen)
    t0 = time.perf_counter()
    m, value = s.search(b, max_depth=depth, on_info=None)
    dt = time.perf_counter() - t0
    return m.uci() if m else None, value, s.nodes, dt


def main():
    print('depth 3 / KingSafety OFF / TacticalChecks OFF vs ON / 2회 반복 중앙값')
    print(f"{'position':<19} {'mode':<5} {'bestmove':<9} {'cp/mate':>8} {'nodes':>10} {'ms':>9} {'NPS':>10}")
    for name, fen in CASES:
        for enabled in (False, True):
            vals = [run_case(fen, enabled, 3) for _ in range(2)]
            move, score, nodes, _ = vals[-1]
            t = statistics.median(v[3] for v in vals)
            print(f'{name:<19} {"ON" if enabled else "OFF":<5} {move or "0000":<9} {score:8d} {nodes:10d} {t*1000:9.1f} {int(nodes/t):10d}', flush=True)


if __name__ == '__main__':
    main()
