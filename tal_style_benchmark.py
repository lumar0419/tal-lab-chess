"""Historical-Mikhail-Tal decision benchmark for the ONE existing chess engine.

This tool does not alter the chess engine's move choice or claim that matching
Tal's historical move is objectively best, engine-strength, or human-likeness.
Positions are reconstructed independently from verified public game scores.

Examples:
  python tal_style_benchmark.py --quick --depth 2
  python tal_style_benchmark.py --profiles baseline,tactical,activity,initiative,combined --depth 3 --json-output tal_report.json
  python tal_style_benchmark.py --case tal_larsen_1965_g10_ply31 --depth 4
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import time

import evaluate
from board import Board, EMPTY, WHITE
from search import Searcher, format_score, mate_plies

HERE = Path(__file__).resolve().parent
PROFILE_FLAGS = {
    'baseline': (False, False, False),
    'tactical': (True, False, False),
    'activity': (False, True, False),
    'initiative': (False, False, True),
    'combined': (True, True, True),
}


def load_data(folder=HERE):
    games = json.loads((Path(folder) / 'tal_games.json').read_text(encoding='utf-8'))['games']
    positions = json.loads((Path(folder) / 'tal_positions.json').read_text(encoding='utf-8'))['positions']
    return games, positions


def validate_data(games, positions):
    """Replay *all* games using our own legal-move engine and verify FEN+UCI.

    Raises AssertionError on source transcription mistakes or stale FENs.
    Independent external legality verification is optional and documented.
    """
    snapshots = {}
    games_by_id = {}
    for game in games:
        gid = game['id']
        if gid in games_by_id:
            raise AssertionError(f'duplicate game id: {gid}')
        games_by_id[gid] = game
        board = Board()
        for ply, token in enumerate(game['uci_moves']):
            if board.parse_uci(token) is None:
                raise AssertionError(f'illegal source move {gid} at ply {ply}: {token}')
            snapshots[(gid, ply)] = board.fen()
            board.push_uci(token)
    seen = set()
    for case in positions:
        cid = case['id']
        if cid in seen:
            raise AssertionError(f'duplicate case id: {cid}')
        seen.add(cid)
        gid, ply = case['game_id'], case['ply_before']
        if gid not in games_by_id:
            raise AssertionError(f'unknown game for {cid}: {gid}')
        game = games_by_id[gid]
        if ply >= len(game['uci_moves']) or ply < 0:
            raise AssertionError(f'invalid ply for {cid}: {ply}')
        if case['fen'] != snapshots[(gid, ply)]:
            raise AssertionError(f'FEN differs from recorded game for {cid}')
        if case['tal_move'] != game['uci_moves'][ply]:
            raise AssertionError(f'Tal move differs from game for {cid}')
        if case['source'] != game['source']:
            raise AssertionError(f'source mismatch: {cid}')
        board = Board(case['fen'])
        if (board.side == WHITE) != (game['tal_color'] == 'white'):
            raise AssertionError(f'wrong player to move: {cid}')
        if board.parse_uci(case['tal_move']) is None:
            raise AssertionError(f'not a legal move: {cid}')
    return len(games), len(positions)


@contextmanager
def profile_settings(profile):
    """Don't leak module-wide evaluation flags into later sessions/tests."""
    tactical, activity, initiative = PROFILE_FLAGS[profile]
    previous = evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY
    try:
        evaluate.ATTACK_ACTIVITY = activity
        evaluate.INITIATIVE = initiative
        evaluate.KING_SAFETY = False  # previously measured regression; deliberately not varied
        yield tactical
    finally:
        evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY = previous


def immediate_signals(fen, move_uci):
    """Cheap descriptive metrics, not proof of a successful Tal-style sacrifice."""
    b = Board(fen)
    move = b.parse_uci(move_uci)
    if move is None:
        raise ValueError(f'illegal move {move_uci} in {fen}')
    mover = b.board[move.frm]
    is_capture = b.board[move.to] != EMPTY or (mover.upper() == 'P' and move.to == b.ep and b.ep != 0)
    initial_attacked = b.is_attacked(move.frm, b.side ^ 1)
    b.make_move(move)
    gives_check = b.in_check()  # side has switched; opponent is now to move
    en_prise = b.is_attacked(move.to, b.side)
    # Tal's famous 21...Nf4 knight was ALREADY attacked on h5; report exposure
    # separately from *new* exposure rather than hide such historical cases.
    return {
        'gives_check': bool(gives_check),
        'captures': bool(is_capture),
        'exposed_to_capture_after': bool(en_prise and mover.upper() in 'NBRQ'),
        'moves_into_attack': bool(en_prise and not initial_attacked and mover.upper() in 'NBRQ'),
        'moved_piece': mover.upper(),
    }


def make_searcher(tactical, tt_size=20000):
    s = Searcher(tt_size=tt_size)
    s.qsearch_quiet_checks = tactical
    return s


def evaluate_case(case, profile, depth=2, include_forced=True):
    """Compare unrestricted move to Tal's historical move, same board/depth/profile.

    Forced Tal score is a separate finite-depth search, not an exact game-theoretic
    score. Different alpha-beta pruning and transposition ordering can affect gaps.
    """
    if depth < 1:
        raise ValueError('depth must be >= 1')
    b = Board(case['fen'])
    state = b.snapshot()
    with profile_settings(profile) as tactical:
        s = make_searcher(tactical)
        t0 = time.perf_counter()
        info = []
        chosen, score = s.search(b, max_depth=depth, on_info=info.append)
        elapsed = time.perf_counter() - t0
        if b.snapshot() != state:
            raise AssertionError(f'Board state mutated: {case["id"]}')
        best_uci = chosen.uci() if chosen else None
        best_pv = ' '.join(m.uci() for m in info[-1].pv) if info else ''
        tal_score = None
        tal_pv = ''
        forced_nodes = None
        if include_forced:
            forced = make_searcher(tactical)
            f_info = []
            forced_move, tal_score = forced.search(b, max_depth=depth,
                                                  root_moves=[case['tal_move']], on_info=f_info.append)
            forced_nodes = forced.nodes
            tal_pv = ' '.join(m.uci() for m in f_info[-1].pv) if f_info else ''
            if forced_move is None or forced_move.uci() != case['tal_move']:
                raise AssertionError('Root-move filter unexpectedly failed')
            if b.snapshot() != state:
                raise AssertionError(f'Board state changed in constrained search {case["id"]}')
        best_signals = immediate_signals(case['fen'], best_uci) if best_uci else None
        tal_signals = immediate_signals(case['fen'], case['tal_move'])
        if tal_score is not None and mate_plies(score) is None and mate_plies(tal_score) is None:
            gap = score - tal_score
        else:
            gap = None
        return {
            'id': case['id'], 'game_id': case['game_id'], 'theme': case['theme'],
            'profile': profile, 'depth': depth, 'fen': case['fen'],
            'historical_san': case['san'], 'historical_uci': case['tal_move'],
            'selected_uci': best_uci, 'exact_historical_match': best_uci == case['tal_move'],
            'selected_score': score, 'selected_score_display': format_score(score),
            'historical_forced_score': tal_score,
            'historical_forced_score_display': format_score(tal_score) if tal_score is not None else None,
            'finite_depth_gap_cp': gap, 'nodes': s.nodes, 'forced_nodes': forced_nodes,
            'elapsed_s': round(elapsed, 4),
            'selected_pv': best_pv, 'historical_pv': tal_pv,
            'selected_signals': best_signals, 'historical_signals': tal_signals,
            'source': case['source'],
        }


def summarize(rows):
    report = {}
    for profile in dict.fromkeys(r['profile'] for r in rows):
        subset = [r for r in rows if r['profile'] == profile]
        n = len(subset)
        report[profile] = {
            'positions': n,
            'historical_move_matches': sum(r['exact_historical_match'] for r in subset),
            'historical_match_rate': round(sum(r['exact_historical_match'] for r in subset) / n, 4) if n else None,
            'selected_checks': sum(r['selected_signals']['gives_check'] for r in subset if r['selected_signals']),
            'selected_captures': sum(r['selected_signals']['captures'] for r in subset if r['selected_signals']),
            'selected_exposed_piece_proxy': sum(r['selected_signals']['exposed_to_capture_after'] for r in subset if r['selected_signals']),
            'selected_moves_into_attack_proxy': sum(r['selected_signals']['moves_into_attack'] for r in subset if r['selected_signals']),
            'total_nodes': sum(r['nodes'] for r in subset),
            'search_time_s': round(sum(r['elapsed_s'] for r in subset), 3),
        }
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description='Historical Tal decision diagnostic (not Elo or objective soundness)')
    ap.add_argument('--depth', type=int, default=2, help='same fixed search depth for all cases')
    ap.add_argument('--profiles', default='baseline,tactical,activity,initiative',
                    help='comma-separated: ' + ','.join(PROFILE_FLAGS))
    ap.add_argument('--case', action='append', help='run only a given exact case ID; repeatable')
    ap.add_argument('--quick', action='store_true', help='one famous attacking decision from each game')
    ap.add_argument('--json-output', help='save detailed results as JSON')
    ap.add_argument('--no-forced', action='store_true', help='skip constrained search of historical move')
    args = ap.parse_args(argv)
    if not 1 <= args.depth <= 8:
        ap.error('--depth must be between 1 and 8 (deep searches may take a long time)')
    profiles = [p.strip() for p in args.profiles.split(',') if p.strip()]
    if not profiles or len(profiles) != len(set(profiles)) or any(p not in PROFILE_FLAGS for p in profiles):
        ap.error('unknown or duplicate profile; choose from ' + ','.join(PROFILE_FLAGS))

    games, cases = load_data()
    validate_data(games, cases)
    if args.case:
        wanted = set(args.case)
        missing = wanted - {c['id'] for c in cases}
        if missing:
            ap.error('unknown case ID: ' + ', '.join(sorted(missing)))
        cases = [c for c in cases if c['id'] in wanted]
    if args.quick:
        cases = [case for case in cases if case.get('featured')]
        if not cases:
            ap.error('no featured historical decisions found')
    print(f'Historic source games: {len(games)}, selected critical decisions: {len(cases)}; depth {args.depth}')
    print('Reference move = historical choice, NOT a proven objectively best move. Engine settings unchanged.')
    rows = []
    for profile in profiles:
        print(f'\n[{profile}]')
        for c in cases:
            r = evaluate_case(c, profile, args.depth, include_forced=not args.no_forced)
            rows.append(r)
            indicator = 'MATCH' if r['exact_historical_match'] else 'other'
            gap = f"gap={r['finite_depth_gap_cp']}cp" if r['finite_depth_gap_cp'] is not None else 'gap=mate-sensitive/not measured'
            print(f" {indicator:5} {c['id']:<34} Tal {c['san']:<8} ({c['tal_move']}) "
                  f"engine {str(r['selected_uci']):<6} {r['selected_score_display']:<6} {gap}", flush=True)
    summary = summarize(rows)
    print('\nSUMMARY (selection on selected historical positions; not general style or Elo):')
    for profile, s in summary.items():
        print(f'  {profile:<11} historical-match {s["historical_move_matches"]}/{s["positions"]} '
              f'checks {s["selected_checks"]} captures {s["selected_captures"]} '
              f'exposed-piece proxy {s["selected_exposed_piece_proxy"]} '
              f'nodes {s["total_nodes"]:,} time {s["search_time_s"]:.2f}s')
    if args.json_output:
        output = {'format_version': 1, 'engine_version': '0.4.7', 'depth': args.depth,
                  'limitations': ['Tal move matching is historical imitation, not proof of quality or human likeness',
                                  'Attack and sacrifice signals are descriptive proxies, not strategic or tactical correctness',
                                  'Root-forced score gaps are finite-depth approximations and may be search-order dependent',
                                  'Some Tal sacrifices were speculative and may not be best under deep analysis'],
                  'summary': summary, 'positions': rows}
        target = Path(args.json_output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Saved:', target)
    return summary


if __name__ == '__main__':
    main()
