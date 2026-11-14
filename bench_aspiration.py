"""Fixed-depth Aspiration ON/OFF benchmark for the ONE chess engine.

Run with reproducible order and independent TT to avoid warmed-cache bias:
    python bench_aspiration.py --depth 5 --repeats 3
    python bench_aspiration.py --depth 5 --quick --json-output aspiration_quick_v0410.json

This is NOT an Elo or human-style benchmark. Default OFF pending controlled games.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from board import Board, START_FEN
from perft import TESTS
from search import ENGINE_VERSION, Searcher
from tal_style_benchmark import load_data


def suite(quick=False):
    _, positions = load_data()
    x = [('start', START_FEN), ('kiwipete', TESTS[1][1]),
         ('position3', TESTS[2][1])]
    if quick:
        x += [('tal_botvinnik', next(p['fen'] for p in positions if p['featured']))]
    else:
        x += [('tal_' + p['id'], p['fen']) for p in positions if p['featured']]
        x += [('italian', 'r1bqk1nr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4')]
    return x


def measure(depth=5, repeats=3, quick=False, window=40):
    out = {'version': ENGINE_VERSION, 'depth': depth, 'repeats': repeats,
           'window_cp': window, 'method': 'alternating runs, independent TT, per-position medians',
           'positions': [], 'all_scores_match': True}
    for name, fen in suite(quick):
        runs = {False: [], True: []}
        for rep in range(repeats):
            for use in ([False, True] if rep % 2 == 0 else [True, False]):
                s=Searcher(tt_size=20000)
                s.aspiration = use
                s.aspiration_window = window
                b=Board(fen)
                snapshot=b.snapshot()
                t=time.perf_counter()
                move,score=s.search(b,max_depth=depth,on_info=None)
                elapsed=time.perf_counter()-t
                assert b.snapshot()==snapshot
                runs[use].append({'move':move.uci() if move else None, 'score':score,
                                  'nodes':s.nodes, 'seconds':elapsed,
                                  'retries':s.aspiration_researches,
                                  'fail_low':s.aspiration_fail_low,
                                  'fail_high':s.aspiration_fail_high})
        same={r['score'] for r in runs[False]} == {r['score'] for r in runs[True]}
        out['all_scores_match'] &= same
        row={'name': name, 'fen': fen, 'scores_match': same}
        for use,label in ((False,'off'),(True,'on')):
            vals=runs[use]
            row[label]={'median_time_s':statistics.median(v['seconds'] for v in vals),
                        'median_nodes':statistics.median(v['nodes'] for v in vals),
                        'median_retries':statistics.median(v['retries'] for v in vals),
                        'moves':sorted(set(v['move'] for v in vals)),
                        'scores':sorted(set(v['score'] for v in vals))}
        out['positions'].append(row)
        print(f"{name:40} {row['off']['median_time_s']:.3f}s -> {row['on']['median_time_s']:.3f}s "
              f"nodes {row['off']['median_nodes']:,.0f}->{row['on']['median_nodes']:,.0f}, "
              f"retries {row['on']['median_retries']:.0f} {'OK' if same else 'MISMATCH'}", flush=True)
    out['median_time_ratio']=statistics.median(
        x['on']['median_time_s']/x['off']['median_time_s'] for x in out['positions'])
    out['median_node_ratio']=statistics.median(
        x['on']['median_nodes']/x['off']['median_nodes'] for x in out['positions'])
    print(f"median relative time: {out['median_time_ratio']:.1%}; "
          f"nodes {out['median_node_ratio']:.1%}")
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--depth',type=int,default=5)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--window',type=int,default=40)
    p.add_argument('--quick',action='store_true')
    p.add_argument('--json-output')
    a=p.parse_args()
    if not 1<=a.depth<=7 or a.repeats<1 or not 1<=a.window<=2000:
        p.error('depth 1..7, repeats>=1, window 1..2000')
    report=measure(a.depth,a.repeats,a.quick,a.window)
    if a.json_output:
        Path(a.json_output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return 0 if report['all_scores_match'] else 1

if __name__=='__main__':
    raise SystemExit(main())
