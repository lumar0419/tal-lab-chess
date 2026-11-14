"""Bounded, reproducible same-engine CPU benchmark; no GPU/Elo claims."""
import platform
import statistics
import time
from board import Board, START_FEN
import evaluate
from search import Searcher

BENCH_ID = 'tal-v084-depth3-mpv3-kiwipete-v2'
POSITIONS = [START_FEN, 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1']

def run_benchmark(repeats=3):
    flags = {key: getattr(evaluate, key) for key in ('ATTACK_ACTIVITY', 'INITIATIVE', 'KING_SAFETY')}
    samples = []
    try:
        for key in flags: setattr(evaluate, key, False)
        for _ in range(repeats):
            elapsed, nodes, results = 0., 0, []
            for fen in POSITIONS:
                evaluate.clear_pawn_cache()
                s = Searcher(tt_size=60_000)
                lines = []
                t = time.perf_counter()
                s.search(Board(fen), max_depth=3, time_limit=10, full_time=True,
                         multipv=3, on_info=None, on_multipv=lambda group: lines.append(group))
                elapsed += time.perf_counter() - t
                nodes += s.nodes
                if not lines or lines[-1][0].depth != 3:
                    raise ValueError('벤치마크 깊이를 완료하지 못했습니다. 자동 선택에 사용하지 않습니다.')
                results.append([(l.pv[0].uci(), l.score) for l in lines[-1]])
            samples.append({'seconds': elapsed, 'nodes': nodes, 'results': results})
    finally:
        for key, value in flags.items(): setattr(evaluate, key, value)
    return {'benchmark_id': BENCH_ID, 'python': platform.python_version(), 'samples': samples,
            'median_seconds': statistics.median(s['seconds'] for s in samples),
            'median_nps': statistics.median(s['nodes']/s['seconds'] for s in samples)}

if __name__ == '__main__':
    import json
    print(json.dumps(run_benchmark(), indent=2))
