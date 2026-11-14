"""v0.4.8: depth-by-depth diagnostics for Tal's historical attacking decisions.

Uses the ONE existing Searcher, never alters its move choice.  Constrained
root searches and historical agreement are *diagnostic*, NOT ground truth.

    python tal_depth_diagnostic.py --quick --profiles baseline,combined --depths 2,3,4 --json-output tal_depth_v048.json
    python tal_depth_diagnostic.py --case tal_larsen_1965_g10_ply31 --depths 2,3,4,5
    python tal_depth_diagnostic.py --quick --depths 2,3 --stockfish /path/to/stockfish --sf-depth 16
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import sys
import time

import evaluate
from board import Board
from search import Searcher, ENGINE_VERSION, format_score, mate_plies
from analyze_sacrifices import material_for, inspect_line, stockfish_review
from tal_style_benchmark import (
    load_data, validate_data, PROFILE_FLAGS, profile_settings, immediate_signals
)

ROOT = Path(__file__).resolve().parent


def depths_from_string(text):
    """Strictly increasing positive depth list; no expensive accidental depth 100."""
    try:
        depths = [int(x.strip()) for x in text.split(',')]
    except ValueError as exc:
        raise ValueError('depths must be comma-separated integers') from exc
    if not depths or any(not 1 <= d <= 7 for d in depths):
        raise ValueError('depths must be in 1..7')
    if sorted(set(depths)) != depths:
        raise ValueError('depths must be unique, in ascending order')
    return depths


def verify_pv(fen, pv):
    """Reject stale/illegal reconstructed principal variations before reporting."""
    board = Board(fen)
    trail = []
    for move in pv:
        if board.parse_uci(move.uci()) is None:
            raise AssertionError(f'illegal PV move {move.uci()} after {trail}')
        board.make_move(move)
        trail.append(move.uci())
    return trail


def run_root(fen, depth, tactical, root_move=None, tt_size=20000, aspiration=False):
    """Fresh independent search/TT per call: same limits for best and forced."""
    board = Board(fen)
    before = board.snapshot()
    searcher = Searcher(tt_size=tt_size)
    searcher.qsearch_quiet_checks = bool(tactical)
    searcher.aspiration = bool(aspiration)
    infos = []
    start = time.perf_counter()
    chosen, score = searcher.search(board, max_depth=depth,
                                    root_moves=[root_move] if root_move else None,
                                    on_info=infos.append)
    elapsed = time.perf_counter() - start
    if board.snapshot() != before:
        raise AssertionError('search mutated board state')
    pv_moves = infos[-1].pv if infos else ([chosen] if chosen is not None else [])
    pv = verify_pv(fen, pv_moves)
    if chosen is not None and pv and chosen.uci() != pv[0]:
        raise AssertionError('PV first move does not match bestmove')
    if root_move is not None and (chosen is None or chosen.uci() != root_move):
        raise AssertionError(f'constrained search ignored historical move {root_move}')
    if not infos or infos[-1].depth != depth:
        # For these four historical positions none is a forced mate. Avoid
        # presenting partially completed or early-terminated results as full.
        raise AssertionError(f'no complete requested depth {depth} search')
    return {
        'move': chosen.uci() if chosen else None,
        'score_cp_or_mate_encoded': score,
        'score_display': format_score(score),
        'completed_depth': infos[-1].depth,
        'nodes': searcher.nodes,
        'elapsed_s': round(elapsed, 5),
        'aspiration_researches': searcher.aspiration_researches,
        'pv': pv,
        'material_delta_by_ply_cp': inspect_line(Board(fen), pv_moves),
    }


def root_static_score(fen, move):
    """Static post-move eval in original mover's perspective; not search score."""
    b = Board(fen)
    m = b.parse_uci(move)
    if m is None:
        raise ValueError(f'illegal move {move}')
    original_material = material_for(b, b.side)
    root_side = b.side
    b.make_move(m)
    after_material = material_for(b, root_side)
    static = -evaluate.evaluate(b)
    # Keep parent immutable by evaluating a fresh board; consistency still checkable.
    return {
        'static_eval_after_move_cp': static,
        'immediate_material_delta_cp': after_material - original_material,
        'signals': immediate_signals(fen, move),
    }


def diagnose_one(case, profile, depths, aspiration=False):
    """Full vs historical root-forced searches, fresh TT, identical profile/depth."""
    with profile_settings(profile) as tactical:
        history_static = root_static_score(case['fen'], case['tal_move'])
        # 초깃값/TT가 없는 첫 정렬: 역사적 수의 탐색 순서 분석용.
        # 높은 순위가 좋은 수라는 뜻은 아니며 깊은 반복 심화에서는 TT가 다시 정렬한다.
        ranking_board = Board(case['fen'])
        legal_moves = set(ranking_board.legal_moves())
        ranked = [m for m in Searcher(tt_size=0).order_moves(
            ranking_board, ranking_board.pseudo_legal_moves(), None, 0)
            if m in legal_moves]
        tal_rank = next(i + 1 for i, m in enumerate(ranked)
                        if m.uci() == case['tal_move'])
        rows = []
        for depth in depths:
            best = run_root(case['fen'], depth, tactical, aspiration=aspiration)
            tal = run_root(case['fen'], depth, tactical, root_move=case['tal_move'],
                           aspiration=aspiration)
            chosen_static = root_static_score(case['fen'], best['move'])
            best_score = best['score_cp_or_mate_encoded']
            tal_score = tal['score_cp_or_mate_encoded']
            mate_sensitive = mate_plies(best_score) is not None or mate_plies(tal_score) is not None
            gap = None if mate_sensitive else best_score - tal_score
            rows.append({
                'depth': depth,
                'selected': best,
                'historical_forced': tal,
                'historical_move_chosen': best['move'] == case['tal_move'],
                'approx_score_gap_cp': gap,
                'mate_sensitive': mate_sensitive,
                'selected_static': chosen_static,
                'warning': 'negative gap from different search order / TT paths' if gap is not None and gap < 0 else None,
            })
    gap_first = rows[0]['approx_score_gap_cp']
    gap_last = rows[-1]['approx_score_gap_cp']
    return {
        'case_id': case['id'],
        'game_id': case['game_id'],
        'theme': case['theme'],
        'fen': case['fen'],
        'historical_san': case['san'],
        'historical_move': case['tal_move'],
        'initial_root_rank': tal_rank,
        'initial_root_legal_count': len(ranked),
        'source': case['source'],
        'profile': profile,
        'aspiration': bool(aspiration),
        'historical_static': history_static,
        'depth_results': rows,
        'gap_trend_first_to_last_cp': None if gap_first is None or gap_last is None else gap_last - gap_first,
        'interpretation': 'Depth/gap trends alone cannot distinguish horizon effects, evaluation bias, and a speculative historical move. Independent stronger analysis is needed.',
    }


def run_diagnostic(cases, profiles, depths, stockfish=None, sf_depth=16, aspiration=False):
    """Separate engine historical comparisons from optional external review."""
    out = []
    external = {}
    for case in cases:
        print(f"\n{case['id']}  Tal {case['san']} ({case['tal_move']})", flush=True)
        for profile in profiles:
            item = diagnose_one(case, profile, depths, aspiration=aspiration)
            out.append(item)
            for x in item['depth_results']:
                gap = ('mate-sensitive' if x['mate_sensitive'] else
                       f"{x['approx_score_gap_cp']:+d}cp")
                a, h = x['selected'], x['historical_forced']
                print(f"  {profile:<10} d{x['depth']}: picked {a['move']:<5} {a['score_display']:>7} | "
                      f"Tal {h['score_display']:>7} | gap {gap:>14} | "
                      f"PV {' '.join(h['pv'][:5])}", flush=True)
            final = item['depth_results'][-1]
            tal_static = item['historical_static']
            chosen_static = final['selected_static']
            print(f"  {profile:<10} static-after: Tal {tal_static['static_eval_after_move_cp']:+d}cp, "
                  f"selected {chosen_static['static_eval_after_move_cp']:+d}cp; "
                  f"Tal PV material change {final['historical_forced']['material_delta_by_ply_cp']}cp; "
                  f"gap change {item['gap_trend_first_to_last_cp']}cp", flush=True)
        if stockfish:
            board = Board(case['fen'])
            best, candidate = stockfish_review(board, [case['tal_move']], stockfish, sf_depth)
            external[case['id']] = {
                'best': best,
                'historical_root_forced': candidate[case['tal_move']],
                'stockfish_depth': sf_depth,
                'note': 'unrestricted and forced-root values are a finite-depth Stockfish diagnostic, not a proof of objective soundness',
            }
            print(f"  Stockfish depth {sf_depth}: best {best['score']} / historical {candidate[case['tal_move']]['score']}", flush=True)
    overview = {}
    for profile in profiles:
        samples = [item for item in out if item['profile'] == profile]
        overview[profile] = {
            'cases': len(samples),
            'historical_choices_at_last_depth': sum(x['depth_results'][-1]['historical_move_chosen'] for x in samples),
            'gaps_narrowed_at_last_depth': sum(x['gap_trend_first_to_last_cp'] is not None
                                                and x['gap_trend_first_to_last_cp'] < 0 for x in samples),
            'gaps_widened_at_last_depth': sum(x['gap_trend_first_to_last_cp'] is not None
                                               and x['gap_trend_first_to_last_cp'] > 0 for x in samples),
        }
    return {
        'schema_version': 1,
        'engine_version': ENGINE_VERSION,
        'overview': overview,
        'utc_created': datetime.now(timezone.utc).isoformat(),
        'python_version': sys.version.split()[0],
        'system': platform.platform(),
        'profiles': profiles,
        'depths': depths,
        'aspiration_enabled': bool(aspiration),
        'cases': out,
        'external_stockfish': external,
        'limitations': [
            'ONE unchanged chess engine; profiles are runtime flags, not separate engines',
            'Tal historical move is NOT an objectively correct answer',
            'A finite-depth root-forced score is NOT the minimax score and can depend on search order',
            'Scores and PVs can change sharply with depth; no attribution to evaluation vs search without further analysis',
            'Material deltas follow truncated PVs and are not a measure of lasting sacrifice compensation',
            'No Elo, human-likeness score, or objective soundness claim is produced',
            'FENs omit historical move/repetition history even when reconstructed from full game scores',
            'Stockfish data only appears if independently run with the requested binary and depth',
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description='Tal historical-move depth and root-forced score diagnosis')
    ap.add_argument('--depths', default='2,3,4', help='ascending unique depths 1..7, comma-separated')
    ap.add_argument('--profiles', default='baseline,combined', help='comma-separated: ' + ','.join(PROFILE_FLAGS))
    ap.add_argument('--quick', action='store_true', help='four featured decisions only')
    ap.add_argument('--aspiration', action='store_true',
                    help='experiment with aspiration windows, same engine (default disabled)')
    ap.add_argument('--case', action='append', help='exact case ID; repeatable')
    ap.add_argument('--json-output', help='write structured diagnostic report')
    ap.add_argument('--stockfish', metavar='PATH', help='optional external full-strength Stockfish executable')
    ap.add_argument('--sf-depth', type=int, default=16, help='independent Stockfish depth')
    args = ap.parse_args(argv)
    try:
        depths = depths_from_string(args.depths)
    except ValueError as exc:
        ap.error(str(exc))
    profiles = args.profiles.split(',')
    if not profiles or any(p not in PROFILE_FLAGS for p in profiles) or len(set(profiles)) != len(profiles):
        ap.error('invalid or duplicate profile in --profiles')
    if not 1 <= args.sf_depth <= 100:
        ap.error('--sf-depth must be 1..100')
    games, cases = load_data()
    validate_data(games, cases)
    if args.case:
        selected = set(args.case)
        missing = selected - {c['id'] for c in cases}
        if missing:
            ap.error('unknown case IDs: ' + ', '.join(sorted(missing)))
        cases = [c for c in cases if c['id'] in selected]
    if args.quick:
        cases = [c for c in cases if c.get('featured')]
    print(f'Tal diagnostic: {len(cases)} historical cases, profiles={profiles}, depths={depths}')
    report = run_diagnostic(cases, profiles, depths, args.stockfish, args.sf_depth,
                            aspiration=args.aspiration)
    if args.json_output:
        destination = Path(args.json_output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Report saved:', destination)
    return report


if __name__ == '__main__':
    main()
