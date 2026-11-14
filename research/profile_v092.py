"""Reproducible CPU profile; run BEFORE changing the engine. No timing assertions."""
import argparse
import cProfile
import json
import platform
import pstats
import time
from pathlib import Path

from board import Board, START_FEN
import evaluate
from search import Searcher

KASPAROV = 'b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--depth', type=int, default=5)
    parser.add_argument('--selective', action='store_true')
    args = parser.parse_args()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    engine = Searcher(tt_size=300000)
    engine.lmr = not args.selective
    engine.selective = args.selective
    board = Board(KASPAROV)
    before = board.snapshot()
    rows = []
    evaluate.clear_pawn_cache()
    profiler = cProfile.Profile()
    start = time.perf_counter()
    profiler.enable()
    engine.search(board, max_depth=args.depth, full_time=True, on_info=lambda i: rows.append({
        'depth': i.depth, 'score': i.score, 'nodes': i.nodes, 'seconds': i.seconds,
        'pv': [m.uci() for m in i.pv]}))
    profiler.disable()
    assert before == board.snapshot()
    profiler.dump_stats(str(destination.with_suffix('.prof')))
    stats = pstats.Stats(profiler)
    functions = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        functions.append(dict(file=Path(filename).name, line=line, function=name,
            calls=calls, primitive=primitive, own_seconds=own, cumulative_seconds=cumulative,
            own_us_per_call=own * 1e6 / calls if calls else 0,
            callers=[dict(file=Path(f[0]).name, function=f[2], stats=list(v))
                     for f, v in callers.items()]))
    result = dict(python=platform.python_version(), implementation=platform.python_implementation(),
                  platform=platform.platform(), depth=args.depth, selective=args.selective,
                  seconds=time.perf_counter()-start, nodes=engine.nodes, rows=rows,
                  functions=sorted(functions, key=lambda f: f['own_seconds'], reverse=True))
    destination.write_text(json.dumps(result, indent=2)+'\n')
    for f in result['functions'][:18]:
        print(f"{f['file']}:{f['function']}: {f['calls']} calls, self={f['own_seconds']:.4f}s, total={f['cumulative_seconds']:.4f}s")


if __name__ == '__main__':
    main()
