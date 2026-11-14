"""PVS-vs-classic alpha-beta fixed-depth benchmark; no external engine required.

Each repetition creates a fresh Searcher and Board, alternating execution order
between PVS OFF and ON. Reports medians (hardware/time-specific, not Elo).

    python bench_pvs.py --depth 4 --repeats 3 --json-output pvs_depth4.json
    python bench_pvs.py --depth 5 --repeats 2 --quick
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from board import Board, START_FEN
from search import Searcher, ENGINE_VERSION
from perft import TESTS
from tal_style_benchmark import load_data


def suites(quick=False):
    _, positions = load_data()
    featured = [x for x in positions if x.get('featured')]
    result = [
        ('start', START_FEN),
        ('kiwipete', TESTS[1][1]),
        ('position3', TESTS[2][1]),
        ('position5', TESTS[4][1]),
        ('position6', TESTS[5][1]),
        ('italian', 'r1bqk1nr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4'),
        ('underpromotion', '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'),
    ]
    if quick:
        return result[:3] + result[5:6]
    result += [('tal_' + x['id'], x['fen']) for x in featured]
    return result


def run_benchmark(depth=4, repeats=3, quick=False):
    out = {'engine_version': ENGINE_VERSION, 'depth': depth, 'repeats': repeats,
           'method': 'fresh TT; alternating order; fixed depth; median of repeated runs',
           'positions': [], 'mismatches': []}
    for name, fen in suites(quick=quick):
        measured = {False: [], True: []}
        for i in range(repeats):
            for flag in ([False, True] if i % 2 == 0 else [True, False]):
                b = Board(fen)
                snapshot = b.snapshot()
                s = Searcher(tt_size=30000)
                s.pvs = flag
                start = time.perf_counter()
                m, score = s.search(b, max_depth=depth, on_info=None)
                elapsed = time.perf_counter() - start
                assert b.snapshot() == snapshot, f'board not restored: {name}'
                measured[flag].append({'move': m.uci() if m else None, 'score': score,
                                       'nodes': s.nodes, 'seconds': elapsed,
                                       'probes': s.pvs_probes, 'researches': s.pvs_researches})
        a, c = measured[False], measured[True]
        # Same score is the essential invariant; different best moves at equal score can be legitimate ties.
        equal_scores = {x['score'] for x in a} == {x['score'] for x in c}
        row = {'name': name, 'fen': fen, 'equal_scores': equal_scores,
               'baseline': {'median_nodes': statistics.median(x['nodes'] for x in a),
                            'median_seconds': statistics.median(x['seconds'] for x in a),
                            'first_move': a[0]['move'], 'score': a[0]['score']},
               'pvs': {'median_nodes': statistics.median(x['nodes'] for x in c),
                       'median_seconds': statistics.median(x['seconds'] for x in c),
                       'first_move': c[0]['move'], 'score': c[0]['score'],
                       'median_probes': statistics.median(x['probes'] for x in c),
                       'median_researches': statistics.median(x['researches'] for x in c)}}
        out['positions'].append(row)
        if not equal_scores:
            out['mismatches'].append(name)
        base = row['baseline']['median_seconds']
        ratio = row['pvs']['median_seconds'] / base if base else 1
        print(f"{name:<31} score {a[0]['score']:+7} vs {c[0]['score']:+7} "
              f"nodes {row['baseline']['median_nodes']:>9,.0f} -> {row['pvs']['median_nodes']:>9,.0f} "
              f"time {base:>6.3f}s -> {row['pvs']['median_seconds']:>6.3f}s "
              f"({ratio:.1%}) {'OK' if equal_scores else 'MISMATCH'}", flush=True)
    # Per-position median ratios avoid giving a high-cost tactical position too much weight.
    out['median_time_ratio'] = statistics.median(
        x['pvs']['median_seconds'] / x['baseline']['median_seconds'] for x in out['positions'])
    out['median_node_ratio'] = statistics.median(
        x['pvs']['median_nodes'] / x['baseline']['median_nodes'] for x in out['positions'])
    out['all_scores_equal'] = not out['mismatches']
    print(f"Median time ratio PVS/baseline: {out['median_time_ratio']:.1%}; "
          f"median node ratio: {out['median_node_ratio']:.1%}; "
          f"scores matched: {len(out['positions']) - len(out['mismatches'])}/{len(out['positions'])}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--depth', type=int, default=4)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--json-output')
    args = ap.parse_args(argv)
    if args.depth < 1 or args.depth > 7 or args.repeats < 1:
        ap.error('depth 1..7 and repeats >= 1 required')
    output = run_benchmark(args.depth, args.repeats, args.quick)
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if not output['all_scores_equal']:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
