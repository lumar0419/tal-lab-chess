"""Discover and verify sacrifices using Tal Lab scores and legal defenses.

The blind search is run first. A reference engine and historical choices are
used only afterwards for reporting, never for Tal's ordering or evaluation.
"""
import argparse
import json
from pathlib import Path
import time

from board import Board
from sacrifice import balance, candidate_evidence, mate_proof, VALUE
from search import MATE, MATE_BOUND, Searcher
from research.measure_search import compare_reference, last, run_search
from research.sacrifice_cases import positions, replay_case
from research.tactical_profiles import PROFILES

ROOT = Path(__file__).resolve().parents[1]
MIN_CONFIRMED_DEPTH = 6
MAX_CP_LOSS = 45
MAX_SCORE_DRIFT = 70
MIN_COMPENSATED_SCORE = -35
MIN_UNFAVORABLE_SCORE = -100
MIN_INFERIORITY = 100
CLEAR_LOSS_OF_ADVANTAGE = 250


def trace(board, pv):
    """Count tactical forcing moves and measure relative material along a legal PV."""
    view = Board(board.fen())
    view.restore(board.snapshot())
    side = view.side
    original = balance(view, side)
    changes = []
    checks = 0
    for uci in pv:
        move = view.parse_uci(uci)
        if move is None or view.outcome() is not None:
            raise ValueError(f'Illegal continuation {uci}')
        attacker_turn = view.side == side
        view.make_move(move)
        if attacker_turn and view.in_check():
            checks += 1
        changes.append(balance(view, side) - original)
    ending = view.outcome() if pv else None
    attacker_win = '1-0' if side == 0 else '0-1'
    return {'material_delta_by_ply': changes, 'attacker_checks': checks,
            'worst_material_delta_cp': min([0] + changes),
            'final_material_delta_cp': changes[-1] if changes else 0,
            'ends_in_attacker_mate': bool(ending and ending[0] == attacker_win)}


def material_evidence(board, move, lines):
    """Local exchange evidence, or a cost appearing in a searched continuation.

    A PV material drop may also be a mistake; the verifier grades compensation.
    The explicit distinction lets delayed costs remain hypotheses.
    """
    offered = candidate_evidence(board, move)
    if offered:
        return {'type': 'legal_immediate_offer', 'acceptances': offered['acceptances']}
    for line in reversed(lines):
        pv = line['pv']
        if len(pv) < 2:
            continue
        profile = trace(board, pv)
        changes = profile['material_delta_by_ply']
        # Ignore transient recaptures: require a non-pawn capture and loss after
        # the next attacking move, after the capture.
        view = Board(board.fen())
        side = view.side
        for i, uci in enumerate(pv):
            candidate = view.parse_uci(uci)
            victim = view.board[candidate.to]
            if (view.side != side and victim.upper() in 'NBRQ' and victim != '.'
                    and changes[i] <= -VALUE['P']
                    and (i+1 < len(changes) and changes[i+1] <= -VALUE['P'])):
                return {'type': 'cost_in_searched_line', 'first_loss_ply': i+1,
                        'piece_lost': victim.upper(), 'line_depth': line['depth']}
            view.make_move(candidate)
    return None


def tal_search(board, *, depth, seconds, multipv=1, forced=None, flags=None):
    from evaluate import clear_pawn_cache
    clear_pawn_cache()
    searcher = Searcher(tt_size=60000)
    for key, value in (flags or {}).items():
        setattr(searcher, key, value)
    groups = []
    before = board.snapshot()
    begin = time.perf_counter()
    searcher.search(board, max_depth=depth, time_limit=seconds, full_time=True,
                    multipv=multipv, root_moves=[forced] if forced else None,
                    on_info=(lambda line: groups.append([line])) if multipv == 1 else None,
                    on_multipv=groups.append if multipv > 1 else None)
    elapsed = time.perf_counter() - begin
    if board.snapshot() != before:
        raise RuntimeError('Search modified root board')
    return {'elapsed': elapsed, 'nodes': searcher.nodes, 'iterations': [
        {'depth': group[0].depth, 'lines': [
            {'depth': line.depth, 'move': line.pv[0].uci(), 'score': line.score,
             'pv': [m.uci() for m in line.pv]} for line in group]}
        for group in groups]}


def prove_short_mate(board, move, plies, *, node_budget=25000):
    """Check every legal defense; return False if the proof budget is exhausted."""
    if plies not in (1, 3, 5):
        return False
    return mate_proof(board, move, plies, node_budget=node_budget)['status'] == 'proved'


def analyze_defenses(board, move, *, depth, seconds, evidence=None, flags=None):
    """Rank defenses with a fresh search from the actual defending side."""
    child = Board(board.fen())
    child.restore(board.snapshot())
    child.push_uci(move)
    acceptances = {item['uci'] for item in (evidence or {}).get('acceptances', ())}
    search_depth = max(1, depth - 1)
    result = tal_search(child, depth=search_depth, seconds=seconds, multipv=3, flags=flags)
    history = []
    for group in result['iterations']:
        lines = []
        for rank, line in enumerate(group['lines'], 1):
            score = -line['score']
            if abs(score) > MATE_BOUND:
                score -= 1 if score > 0 else -1
            kind = 'unclassified'
            if acceptances:
                kind = 'accepts' if line['move'] in acceptances else 'declines'
            lines.append(dict(rank=rank, move=line['move'], attacker_score=score,
                              pv=[move]+line['pv'], response=kind))
        history.append(dict(depth=group['depth'], lines=lines))
    final = history[-1] if history else {'depth': 0, 'lines': []}
    return dict(root='after_candidate', depth=final['depth'], max_depth=search_depth,
                seconds_limit=seconds, elapsed=result['elapsed'], nodes=result['nodes'],
                legal_replies=len(child.legal_moves()), lines=final['lines'], iterations=history,
                scope='All legal defenses eligible. Up to three completed lines shown.')


def candidate_history(board, move, unrestricted, forced):
    """Describe each completed depth without promoting a provisional verdict."""
    blind = {group['depth']: group['lines'] for group in unrestricted['iterations']}
    forced_by_depth = {group['depth']: group['lines'][0] for group in forced['iterations']}
    history = []
    for depth in sorted(blind.keys() | forced_by_depth.keys()):
        ranked = next(((rank, line) for rank, line in enumerate(blind.get(depth, ()), 1)
                       if line['move'] == move), None)
        forced_line = forced_by_depth.get(depth)
        row = dict(depth=depth, unrestricted_rank=ranked[0] if ranked else None,
                   unrestricted_score=ranked[1]['score'] if ranked else None,
                   unrestricted_pv=ranked[1]['pv'] if ranked else None,
                   unrestricted_completed=depth in blind)
        if forced_line:
            pv = forced_line['pv']
            row.update(forced_score=forced_line['score'], forced_pv=pv,
                       pv_defense=pv[1] if len(pv)>1 else None,
                       material_and_checks=trace(board, pv))
        history.append(row)
    return history


def classify(board, move, unrestricted, forced, defenses=None, *, evidence=None):
    forced_lines = [group['lines'][0] for group in forced['iterations']]
    if evidence is None:
        evidence = material_evidence(board, move, forced_lines)
    data = {'move': move, 'status': 'no_sacrifice_evidence', 'evidence': evidence,
            'comparison': [], 'profile': None, 'best_defense': None,
            'defenses': defenses, 'confidence': 'insufficient_evidence',
            'verification': {'scope': 'bounded_search', 'proof': False,
                             'limitations': ['Scores and principal variations are depth-limited.',
                                             'Shown defenses are the best found within that search.']}}
    if not evidence:
        return data
    data['status'] = 'sacrifice_candidate'
    data['confidence'] = 'provisional'
    best_by_depth = {group['depth']: group['lines'][0] for group in unrestricted['iterations']}
    for line in forced_lines:
        best = best_by_depth.get(line['depth'])
        if not best:
            continue
        score, best_score = line['score'], best['score']
        mate = abs(score) > MATE_BOUND or abs(best_score) > MATE_BOUND
        data['comparison'].append({'depth': line['depth'], 'forced_score': score,
                                   'best_score': best_score, 'best_move': best['move'],
                                   'cp_loss': max(0, best_score-score) if not mate else None})
    if forced_lines:
        line = forced_lines[-1]
        data['profile'] = trace(board, line['pv'])
        data['best_defense'] = line['pv'][1] if len(line['pv']) >= 2 else None
    if defenses and defenses['lines']:
        data['independent_best_defense'] = defenses['lines'][0]['move']
    if not data['comparison']:
        return data
    comparable = data['comparison']
    deepest = comparable[-1]
    # A forcing mate can be verified earlier than a centipawn estimate, but
    # only if the scored line reaches checkmate at the claimed distance.
    line = next(item for item in forced_lines if item['depth'] == deepest['depth'])
    mate_profile = trace(board, line['pv'])
    if (line['score'] > MATE_BOUND and line['score'] >= deepest['best_score']
            and mate_profile['ends_in_attacker_mate']
            and len(line['pv']) == MATE-line['score']
            and prove_short_mate(board, move, MATE-line['score'])):
        data['status'] = 'verified_tactical_sacrifice'
        data['confidence'] = 'proof_within_scope'
        data['verification'] = {'scope': 'all_legal_defenses_forced_mate',
                                'proof': True, 'mate_plies': MATE-line['score'],
                                'max_proof_plies': 5, 'node_budget': 25000}
        data['basis'] = 'exhaustive_short_mate_after_candidate'
        return data
    if len(comparable) < 2 or deepest['depth'] < MIN_CONFIRMED_DEPTH:
        return data
    previous = comparable[-2]
    if deepest['depth'] != previous['depth']+1:
        return data
    if all(x['forced_score'] < -MATE_BOUND for x in (previous, deepest)):
        data['status'] = 'unfavorable_sacrifice'
        data['basis'] = 'forced_mate_against_at_two_depths'
        return data
    if any(x['cp_loss'] is None for x in (previous, deepest)):
        return data
    if all(x['cp_loss'] >= CLEAR_LOSS_OF_ADVANTAGE for x in (previous, deepest)):
        data['status'] = 'unfavorable_sacrifice'
        data['basis'] = 'substantial_advantage_lost_at_two_matched_depths'
        return data
    if (abs(deepest['forced_score']-previous['forced_score']) > MAX_SCORE_DRIFT
            or abs(deepest['best_score']-previous['best_score']) > MAX_SCORE_DRIFT):
        return data
    if all(x['forced_score'] >= MIN_COMPENSATED_SCORE and x['cp_loss'] <= MAX_CP_LOSS
           for x in (previous, deepest)) and (
               data['profile']['attacker_checks'] >= 2
               or data['profile']['final_material_delta_cp'] >= -35
               or deepest['forced_score'] >= 75):
        # Stability in one PV is supporting evidence, not a tactical proof.
        # Require a fresh defender search with adequate completed depth.
        if defenses and defenses['depth'] >= deepest['depth'] - 1 and defenses['lines']:
            weakest = min(item['attacker_score'] for item in defenses['lines'])
            if weakest >= MIN_COMPENSATED_SCORE and abs(weakest-deepest['forced_score']) <= MAX_SCORE_DRIFT:
                data['status'] = 'engine_supported_sacrifice'
                data['confidence'] = 'bounded_engine_support'
                data['basis'] = 'matched_depths_and_independent_defender_search'
    elif all(x['forced_score'] <= MIN_UNFAVORABLE_SCORE and x['cp_loss'] >= MIN_INFERIORITY
             for x in (previous, deepest)):
        data['status'] = 'unfavorable_sacrifice'
        data['basis'] = 'negative_and_inferior_at_two_matched_depths'
    return data


def diagnose(case, blind, reference, probes):
    """Report evidence for a suspected cause without pretending to isolate it."""
    historical = case['historical_uci']
    found = next((i for i, line in enumerate(last(blind)['lines'], 1)
                  if line['move'] == historical), None)
    if found:
        return ['historical_top3']
    result = []
    score = reference['forced_historical']
    best = reference['candidates'][0]
    if ((best['cp'] is not None and score['cp'] is not None and best['cp'] - score['cp'] >= 100)
            or (best['mate'] is not None and best['mate'] > 0 and score['mate'] is None)):
        result.append('reference_prefers_other_move')
    if any(any(line['move'] == historical for line in group['lines'])
           for group in blind['iterations']):
        result.append('ranking_unstable_across_depth')
    if last(blind)['depth'] < MIN_CONFIRMED_DEPTH:
        result.append('depth_limited')
    for name, probe in probes.items():
        # Match depth, otherwise a result change is just a time/depth confound.
        by_depth = {group['depth']: group['lines'] for group in blind['iterations']}
        for group in probe['iterations']:
            old = by_depth.get(group['depth'])
            if old and all(line['move'] != historical for line in old):
                if any(line['move'] == historical for line in group['lines']):
                    result.append(name + '_sensitive')
                    break
    if not result:
        result.append('evaluation_or_search_unresolved')
    return result


def discover(board, depth, seconds, *, extra_moves=(), multipv=3, flags=None):
    blind = tal_search(board, depth=depth, seconds=seconds, multipv=multipv, flags=flags)
    candidates = last(blind)['lines']
    # Additional moves are verified only after unrestricted discovery.
    evaluations = {}
    for move in dict.fromkeys([line['move'] for line in candidates] + list(extra_moves)):
        if board.parse_uci(move) is None:
            raise ValueError(f'Illegal candidate {move}')
        forced = tal_search(board, depth=depth, seconds=seconds, forced=move, flags=flags)
        evidence = material_evidence(board, move, [group['lines'][0] for group in forced['iterations']])
        defenses = (analyze_defenses(board, move, depth=depth, seconds=seconds,
                                     evidence=evidence, flags=flags) if evidence else None)
        judgment = classify(board, move, blind, forced, defenses, evidence=evidence)
        evaluations[move] = {'forced': forced, 'judgment': judgment,
                             'depth_history': candidate_history(board, move, blind, forced)}
    return blind, evaluations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stockfish')
    parser.add_argument('--fen', help='Analyze a custom position using Tal Lab alone.')
    parser.add_argument('--move', action='append', default=[], help='Optional UCI move to verify after discovery.')
    parser.add_argument('--multipv', type=int, choices=range(1, 6), default=3)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument('--profile', choices=('quiet', 'continuation', 'bridge', 'forcing', 'forcing_bridge',
                                                  'selective'))
    profiles.add_argument('--check-continuation', action='store_true',
                        help='Add up to two quiet checks in eligible quiescence lines.')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--seconds', type=float, default=3.0)
    parser.add_argument('--reference-seconds', type=float, default=1.0)
    parser.add_argument('--depth', type=int, default=8)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', action='append', help='Repeat to select several case IDs.')
    args = parser.parse_args()
    if not 0 < args.seconds <= 60 or not 0 < args.reference_seconds <= 60 or not 1 <= args.depth <= 12:
        parser.error('seconds must be in (0, 60] and depth in [1, 12]')
    flags = PROFILES[args.profile or ('continuation' if args.check_continuation else 'candidate')]
    if args.fen:
        board = Board(args.fen)
        blind, evaluations = discover(board, args.depth, args.seconds,
                                      extra_moves=args.move, multipv=args.multipv, flags=flags)
        report = {'fen': board.fen(), 'seconds_per_search': args.seconds,
                  'max_depth': args.depth, 'search_options': flags,
                  'blind': blind, 'evaluations': evaluations}
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        return
    if not args.stockfish:
        parser.error('historical comparison requires --stockfish, or use --fen')
    import chess.engine
    cases = positions()
    if args.case:
        cases = [case for case in cases if any(fragment in case['id'] for fragment in args.case)]
    if not cases:
        parser.error('no cases selected')
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        engine.configure({'Threads': 1, 'Hash': 32})
        report = {'tal_seconds_per_search': args.seconds, 'tal_max_depth': args.depth,
                  'search_options': flags,
                  'reference': {'engine': engine.id, 'seconds_per_search': args.reference_seconds,
                                'threads': 1, 'hash_mb': 32}, 'cases': []}
        for case in cases:
            board = replay_case(case)
            historic = case['historical_uci']
            blind, evaluations = discover(board, args.depth, args.seconds,
                                          extra_moves=[historic], multipv=args.multipv, flags=flags)
            discovered = last(blind)['lines']
            reference = compare_reference(engine, board.fen(), args.reference_seconds, historic)
            probes = {}
            if all(line['move'] != historic for line in discovered):
                for name, probe_flags in [('move_order', {'tactical_ordering': True}),
                                          ('lmr', {'lmr': True}),
                                          ('quiet_checks', {'qsearch_quiet_checks': True})]:
                    probes[name] = tal_search(board, depth=args.depth, seconds=args.seconds,
                                              multipv=args.multipv, flags=probe_flags)
            # A previous checkout may not implement the new reply filter.
            baseline_flags = {key: value for key, value in flags.items() if key != 'qsearch_forcing_replies'}
            baseline = (run_search(args.baseline, board.fen(), args.depth, args.multipv, args.seconds,
                                   flags=baseline_flags,
                                   history=case.get('history'))
                        if args.baseline else None)
            row = {'case': case, 'blind': blind, 'evaluations': evaluations,
                   'reference': reference, 'baseline': baseline, 'probes': probes,
                   'baseline_search_options': baseline_flags if baseline else None,
                   'diagnosis': diagnose(case, blind, reference, probes)}
            report['cases'].append(row)
            print(case['id'], last(blind)['depth'], row['diagnosis'],
                  evaluations[historic]['judgment']['status'], flush=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
