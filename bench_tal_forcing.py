"""v0.4.11 optional tactical ordering/check-continuation diagnostics, one engine.

  python bench_tal_forcing.py --depth 4 --output tal_forcing_v0411.json
  python bench_tal_forcing.py --depth 3 --quick

This is NOT an Elo test and historical-move agreement is NOT proof of soundness.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import statistics
import sys
import time

from board import Board, START_FEN
from perft import TESTS
from search import ENGINE_VERSION, Searcher
from tal_style_benchmark import load_data


def tal_order_rank(board, historical, tactical=False):
    s = Searcher(tt_size=0)
    moves = board.pseudo_legal_moves()
    candidates = set(s._quiet_check_candidates(board, moves=moves)) if tactical else None
    ordered = s.order_moves(board, moves, None, 0, candidates)
    legal = set(board.legal_moves())
    sorted_legal = [m.uci() for m in ordered if m in legal]
    return sorted_legal.index(historical) + 1, len(sorted_legal)


def measure(fen, depth, mode, tt_entries):
    b = Board(fen)
    before = b.snapshot()
    s = Searcher(tt_size=tt_entries)
    if mode == 'ordering':
        s.tactical_ordering = True
    elif mode == 'quiet_checks':
        s.qsearch_quiet_checks = True
    elif mode == 'continuation':
        s.qsearch_quiet_checks = True
        s.check_continuation = True
    elif mode == 'combined':
        s.tactical_ordering = True
        s.qsearch_quiet_checks = True
        s.check_continuation = True
    t = time.perf_counter()
    best, score = s.search(b, max_depth=depth, on_info=None)
    sec = time.perf_counter() - t
    if before != b.snapshot():
        raise RuntimeError('search mutated board')
    if best not in b.legal_moves():
        raise RuntimeError('search returned an illegal move')
    return {
        'bestmove': best.uci(), 'score_cp_or_mate_encoded': score,
        'nodes': s.nodes, 'wall_seconds': round(sec, 6),
        'nps': round(s.nodes / max(sec, 1e-9)),
        'ordering_nodes': s.tactical_order_nodes,
        'ordering_check_candidates': s.tactical_order_candidates,
        'continuation_nodes': s.check_continuation_nodes,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='Tactical ordering/check continuation micro-benchmark')
    ap.add_argument('--depth', type=int, default=4)
    ap.add_argument('--quick', action='store_true', help='start + two historic Tal positions')
    ap.add_argument('--output', type=Path, help='optional results JSON')
    ap.add_argument('--tt-entries', type=int, default=40000)
    args = ap.parse_args(argv)
    if not 1 <= args.depth <= 6:
        ap.error('depth must be 1..6')
    if args.tt_entries < 100:
        ap.error('tt-entries should be >=100')
    _, all_cases = load_data()
    featured = [x for x in all_cases if x.get('featured')]
    cases = [{'id':'startpos', 'fen':START_FEN}, {'id':'kiwipete','fen':TESTS[1][1]}]
    cases += featured[:2] if args.quick else featured
    modes = ('baseline', 'ordering', 'quiet_checks', 'continuation', 'combined')
    rows = []
    for case in cases:
        print('\n' + case['id'], flush=True)
        ranks = None
        if 'tal_move' in case:
            board = Board(case['fen'])
            ranks = dict(zip(('baseline', 'ordering'),
                             (tal_order_rank(board, case['tal_move'], False)[0],
                              tal_order_rank(board, case['tal_move'], True)[0])))
        results = {}
        for mode in modes:
            result = measure(case['fen'], args.depth, mode, args.tt_entries)
            results[mode] = result
            print(f"  {mode:<14} {result['bestmove']:>5} score {result['score_cp_or_mate_encoded']:>6} "
                  f"nodes {result['nodes']:>8} time {result['wall_seconds']:.3f}s", flush=True)
        rows.append({'id':case['id'],'fen':case['fen'],
                     'historical_move':case.get('tal_move'),
                     'historical_initial_rank':ranks,'modes':results})
    soundness = {
        'all_ordering_scores_equal_baseline': all(r['modes']['ordering']['score_cp_or_mate_encoded'] ==
            r['modes']['baseline']['score_cp_or_mate_encoded'] for r in rows),
        'all_ordering_moves_equal_baseline': all(r['modes']['ordering']['bestmove'] ==
            r['modes']['baseline']['bestmove'] for r in rows),
    }
    timed = [r for r in rows if r['modes']['baseline']['wall_seconds'] > 0.03]
    ratio = [r['modes']['ordering']['wall_seconds']/r['modes']['baseline']['wall_seconds'] for r in timed]
    report = {
        'schema_version': 1, 'engine_version': ENGINE_VERSION, 'created_utc': datetime.now(timezone.utc).isoformat(),
        'python':sys.version.split()[0], 'platform':platform.platform(), 'depth':args.depth,
        'tt_entries':args.tt_entries, 'modes':modes,'results':rows,
        'validation':soundness,
        'ordering_time_ratio_median': round(statistics.median(ratio),4) if ratio else None,
        'limitations': [
            'Each mode uses the SAME engine with fresh TT; not separately developed engines.',
            'No actual Stockfish games were played; no Elo or human-likeness conclusion.',
            'Initial ordering ranks are before TT and history learning.',
            'One sample per mode has CPU noise; repeat before accepting performance claims.',
            'Check continuation can change qsearch semantics; do NOT expect equal scores to baseline.',
            'The full set of Tal moves is style reference, not an objectively correct move list.',
        ]
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Saved',args.output)
    return report


if __name__ == '__main__':
    main()
