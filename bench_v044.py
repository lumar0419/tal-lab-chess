"""Measured comparisons within ONE engine; no Stockfish or Elo claims.
Run: python bench_v044.py
Benchmarks should be repeated on the target machine before drawing performance conclusions.
"""
import time
from pathlib import Path
import evaluate
from board import Board
from search import Searcher, INF

FENS = [f for f in (Path(__file__).parent / 'v044_positions.txt').read_text().splitlines()
        if f and not f.startswith('#')]


def quiet_bench():
    fens = FENS[:35]
    print('Quiet-check filter (same tactical option ON; each position is searched to completion)')
    results = []
    for fast in (False, True):
        t = time.perf_counter()
        nodes = 0
        values = []
        for fen in fens:
            s = Searcher(tt_size=0)
            s.qsearch_quiet_checks = True
            s.qsearch_fast_checks = fast
            b = Board(fen)
            values.append(s.quiesce(b, -INF, INF, 0))
            nodes += s.nodes
        dt = time.perf_counter() - t
        results.append(values)
        print(f'  {"prefilter ON " if fast else "prefilter OFF"}: {dt:.3f}s, {nodes:,} nodes, {len(fens)} positions')
    print('  scores identical:', results[0] == results[1])


def activity_bench():
    print('AttackActivity static evaluation timing (1000 evaluations per variant)')
    fens = FENS[:24]
    try:
        for on in (False, True):
            evaluate.ATTACK_ACTIVITY = on
            # warm-up first
            for fen in fens:
                evaluate.evaluate(Board(fen))
            boards = [Board(fen) for fen in fens]
            t = time.perf_counter()
            checksum = 0
            for i in range(1000):
                checksum += evaluate.evaluate(boards[i % len(boards)])
            dt = time.perf_counter() - t
            print(f'  {"ON " if on else "OFF"}: {dt:.3f}s ({dt * 1000:.3f} ms / 1000), checksum={checksum}')
    finally:
        evaluate.ATTACK_ACTIVITY = False


if __name__ == '__main__':
    quiet_bench()
    activity_bench()
