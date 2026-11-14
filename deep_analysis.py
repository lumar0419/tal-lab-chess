"""Time-budgeted analysis using Tal Lab's own search and legal-move generator."""
import argparse
import json
import math
import time

from board import Board, H_MOVE, WHITE
from sacrifice import ProofInterrupted, _offer_evidence, balance, mate_proof
from search import MAX_PLY, Searcher, TimeUp, mate_plies

DEEP_SECONDS = (60, 180, 300, 600)
VERIFY_MAX_PLY = 7
PROFILES = ('tactical', 'conservative', 'full', 'selective')


def make_searcher(profile='conservative'):
    if profile not in PROFILES:
        raise ValueError('알 수 없는 심층 탐색 프로필입니다.')
    searcher = Searcher(tt_size=300_000)
    searcher.tt.preserve_deeper = True
    searcher.lmr = profile == 'conservative'
    searcher.selective = profile == 'selective'
    searcher.set_tactical(profile == 'tactical')
    return searcher


def _iteration(info, white_to_move):
    return {'depth': info.depth, 'score': info.score if white_to_move else -info.score,
            'nodes': info.nodes, 'seconds': round(info.seconds, 3),
            'pv': [move.uci() for move in info.pv]}


def _material_trace(board, pv):
    side = board.side
    before = balance(board, side)
    view = Board(board.fen())
    view.restore(board.snapshot())
    changes, losses = [], []
    for token in pv:
        move = view.parse_uci(token)
        if move is None:
            raise ValueError(f'Illegal principal variation move {token}')
        victim = view.board[move.to]
        if view.side != side and victim.upper() in ('N', 'B', 'R', 'Q'):
            losses.append((len(changes), victim.upper()))
        view.make_move(move)
        changes.append(balance(view, side) - before)
    sustained = next(({'ply': index + 1, 'piece': piece}
                      for index, piece in losses if index + 1 < len(changes)
                      and changes[index] <= -100 and changes[index + 1] <= -100), None)
    return {'changes_cp': changes, 'low_cp': min([0, *changes]),
            'last_cp': changes[-1] if changes else 0, 'sustained_piece_loss': sustained}


def _compare(lines, reference, white_to_move):
    ref = {line['depth']: line for line in reference}
    for line in reversed(lines):
        comparable = ref.get(line['depth'])
        if comparable:
            return {'depth': line['depth'], 'score': line['score'],
                    'reference_score': comparable['score'],
                    'delta_for_mover': (line['score'] - comparable['score']) *
                                       (1 if white_to_move else -1)}
    return None


def _defense_need(item):
    """Uncertainty, applied equally to sacrifice and ordinary candidates."""
    rows = item['iterations']
    scores = [r['score'] for r in rows[-3:]]
    swing = max(scores)-min(scores) if scores else 0
    replies = {r['pv'][1] for r in rows[-3:] if len(r['pv']) > 1}
    comparison = item.get('comparison')
    close = comparison is not None and abs(comparison['delta_for_mover']) <= 80
    return 1 + min(swing, 400)/200 + int(len(replies)>1) + int(close)


def _defense_consistency(candidate_rows, defense_rows, root_in_check=False):
    """Compare only matching nominal horizons, including the root extension.

    Selective depth is explicitly not an exhaustive full-width horizon.
    Independent re-rooting changes TT/order and resets the extension context.
    """
    offset = 1-int(root_in_check)  # default unlimited check extension at root
    pairs = [(c,d) for c in candidate_rows for d in defense_rows
             if c['depth'] == d['depth']+offset and len(c['pv'])>1 and d['pv']]
    if not pairs:
        return {'status':'insufficient_common_depth', 'depth_offset':offset}
    c,d = max(pairs,key=lambda pair: pair[0]['depth'])
    score = d['score']
    if mate_plies(score) is not None:
        score += -1 if score>0 else 1  # include the candidate's first ply
    return dict(status='agrees' if c['pv'][1]==d['pv'][0] and c['score']==score else 'disagrees',
                candidate_depth=c['depth'], defense_depth=d['depth'],
                candidate_reply=c['pv'][1], independent_reply=d['pv'][0],
                candidate_score=c['score'], independent_score=score,
                reply_agrees=c['pv'][1]==d['pv'][0], score_delta=score-c['score'])


def _verify_defense(item, root_rows, root_in_check=False):
    """A shallower comparison agreement must not certify a deeper root PV."""
    candidate_rows = item['iterations']
    matching_root = [row for row in root_rows if row['pv'] and row['pv'][0]==item['move']]
    item['consistency'] = _defense_consistency(candidate_rows,item['defenses'],root_in_check)
    item['root_consistency'] = (_defense_consistency(matching_root,item['defenses'],root_in_check)
                                if matching_root else None)
    item['required_defense_depth'] = max(
        (r['depth'] for r in [*candidate_rows,*matching_root]),default=1)-1+int(root_in_check)
    item['deepest_defense_verified'] = bool(item['defenses'] and
        item['defenses'][-1]['depth']>=item['required_defense_depth'] and
        item['consistency']['status']=='agrees' and
        (item['root_consistency'] is None or item['root_consistency']['status']=='agrees'))
    if 'reply_agrees' in item['consistency']:
        item['defense_agrees_at_depth'] = item['consistency']['reply_agrees']


def analyze_deep(board, seconds, *, profile='conservative', candidate=None, cancel_check=None,
                 on_root=None, on_progress=None, max_depth=MAX_PLY, adaptive=True):
    """Search the whole root, compare forced moves, then re-root at defenses.

    Each score uses white's perspective. A matched comparison is published only
    when both restricted searches completed the same nominal depth.
    """
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('심층 분석에는 양의 시간 예산이 필요합니다.')
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_PLY:
        raise ValueError('심층 분석 최대 깊이가 범위를 벗어났습니다.')
    if board.outcome() is not None:
        raise ValueError('이미 종료된 국면입니다.')
    forced = board.parse_uci(candidate) if candidate else None
    if candidate and forced is None:
        raise ValueError('지정한 후보 수가 합법수가 아닙니다.')
    started = time.monotonic()
    deadline = started + seconds
    searcher = make_searcher(profile)
    white_to_move = board.side == WHITE
    report = {'fen': board.fen(), 'history': [entry[H_MOVE].uci() for entry in board.history],
              'profile': profile, 'budget': seconds, 'root': [], 'screen': [],
              'offers_found': 0, 'screen_complete': False, 'candidates': [],
              'phase': 'root', 'attempting': 0, 'elapsed': 0, 'outcome': None}
    report['adaptive'] = adaptive
    report['depth_kind'] = 'full_width' if profile=='full' else 'selective'

    def cancelled():
        return cancel_check is not None and cancel_check()

    def expired():
        return time.monotonic() >= deadline or cancelled()

    def publish(phase):
        report['phase'] = phase
        report['elapsed'] = round(time.monotonic() - started, 3)
        if on_progress:
            on_progress(report)

    def run(engine, view, budget, *, moves=None, count=1, depth=max_depth, phase, callback=None):
        attempted_proofs = set()
        rows = []
        limit = min(budget, deadline - time.monotonic())
        if limit <= 0 or cancelled():
            return rows

        phase_deadline = min(deadline, time.monotonic() + limit)

        def confirmed_mate(move, score, plies):
            if score <= 0 or plies > VERIFY_MAX_PLY or move is None:
                return False
            key = move.uci(), plies
            if key in attempted_proofs:
                return False
            attempted_proofs.add(key)
            proof = mate_proof(view, key[0], plies, deadline=phase_deadline, cancel_check=cancelled)
            if phase == 'root':
                report['root_proof'] = {**proof, 'move': key[0]}
            return proof['status'] == 'proved'

        def completed(group):
            lines = [_iteration(info, view.side == WHITE) for info in group]
            rows.append(lines[0] if count == 1 else lines)
            if phase == 'root':
                report['root'] = rows
                if lines[0]['pv']:
                    report['root_move'] = lines[0]['pv'][0]
                if on_root:
                    on_root(group[0])
            if callback:
                callback(rows)
            publish(phase)

        def iteration(depth):
            report['attempting'] = depth
            if cancelled():
                raise TimeUp
            publish(phase)

        engine.search(view, max_depth=depth, time_limit=limit, on_iteration=iteration,
                      full_time=True, root_moves=moves, multipv=count, cancel_check=expired,
                      mate_stop=confirmed_mate,
                      on_info=(lambda info: completed([info])) if count == 1 else None,
                      on_multipv=completed if count > 1 else None)
        return rows

    run(searcher, board, seconds * .64, phase='root')
    if 'root_move' in report and not expired():
        reference = report['root_move']
        offers = {}
        scan_deadline = min(deadline, time.monotonic() + seconds * .03)

        def stop_scan():
            return expired() or time.monotonic() >= scan_deadline

        publish('screen')
        scan_complete = True
        legal = board.legal_moves()
        for move in legal:
            if stop_scan():
                scan_complete = False
                break
            try:
                offered = _offer_evidence(board, move, stop_scan)
            except ProofInterrupted:
                scan_complete = False
                break
            except ValueError:  # Exchange node budget exceeded for this move.
                scan_complete = False
                continue
            if offered:
                offers[move.uci()] = offered
        report.update(offers_found=len(offers), screen_complete=scan_complete)

        # TT entries below the unchanged root can guide screening and forced
        # searches. The unrestricted root score remains untouched.
        offer_moves = [move for move in offers if move != reference]
        if offer_moves:
            report['screen'] = run(searcher, board, seconds * .08, moves=offer_moves,
                                   count=min(2, len(offer_moves)), depth=min(7, max_depth),
                                   phase='screen', callback=lambda rows: report.update(screen=rows))
        screened = report['screen'][-1] if report['screen'] else []
        if screened and isinstance(screened, dict):
            screened = [screened]
        earlier_best = next((row['pv'][0] for row in reversed(report['root'])
                             if row['pv'][0] != reference), None)
        shortlist = dict.fromkeys(move for move in (
            reference, forced.uci() if forced else None,
            *(line['pv'][0] for line in screened), earlier_best) if move)
        if len(shortlist) == 1 and len(legal) > 1 and not expired():
            alternatives = (move for move in legal if move.uci() != reference)
            other = run(searcher, board, seconds * .06, moves=alternatives,
                        depth=min(6, max_depth), phase='screen')
            if other:
                shortlist[other[-1]['pv'][0]] = None
        shortlist = list(shortlist)[:3]
        remaining = max(0, deadline - time.monotonic())
        # Keep the 64% unrestricted-root guarantee and equal comparison budgets.
        # Reserve more time for independent defense, where v0.9.1 could report
        # a shallower, contradictory reply after a deeper candidate search.
        comparison_budget = remaining * (.55 if adaptive else .72) / len(shortlist)
        seed = searcher.tt.slots.copy()
        generation, size = searcher.tt.generation, len(searcher.tt)
        searcher.tt_current_generation_only = True
        searcher.tt.preserve_deeper = False
        for move in shortlist:
            if expired():
                break
            item = {'move': move, 'offer': offers.get(move), 'reference': move == reference,
                    'iterations': [], 'comparison': None, 'defenses': [], 'proof': None,
                    'verification': 'pending', 'time_limit': round(comparison_budget, 3)}
            report['candidates'].append(item)
            # Identical TT seed and time for each candidate. Earlier stages
            # can order moves here but cannot return a deeper score as a bound.
            searcher.tt.slots = seed.copy()
            searcher.tt.count = size
            searcher.tt.generation = generation
            run(searcher, board, comparison_budget, moves=[move], phase='compare',
                callback=lambda rows: item.update(iterations=rows))
        del seed
        if report['candidates']:
            reference_rows = report['candidates'][0]['iterations']
            for item in report['candidates']:
                item['comparison'] = _compare(item['iterations'], reference_rows, white_to_move)
                item['verification'] = 'matched_depth' if item['comparison'] else 'pending'
                if item['iterations']:
                    item['material'] = _material_trace(board, item['iterations'][-1]['pv'])

        # Changed root and history: separate tables for independent defense
        # search. All opponent replies are legal candidates, including declines.
        remaining = max(0, deadline - time.monotonic())
        defense_budget = remaining * .92 / len(shortlist)
        needs = [_defense_need(item) for item in report['candidates']]
        defense_limits = [(remaining*.92*(.6/len(needs)+.4*need/sum(needs)))
                          for need in needs] if adaptive else [defense_budget]*len(needs)
        for item, defense_budget in zip(report['candidates'], defense_limits):
            if expired():
                break
            child = Board(board.fen())
            child.restore(board.snapshot())
            child.push_uci(item['move'])
            offered = item['offer']
            item['legal_replies'] = len(child.legal_moves())
            item['defense_time_limit'] = round(defense_budget, 3)
            terminal = child.outcome()
            if terminal:
                item['terminal'] = terminal
            else:
                defender = make_searcher(profile)
                item['draw_claim'] = bool(child.claimable_draw() or defender._can_announce_draw(child))
                run(defender, child, defense_budget, phase='defense',
                    callback=lambda rows: item.update(defenses=rows))
                if item['defenses']:
                    item['verification'] = 'defense_searched'
                    last_defense = item['defenses'][-1]
                    item['material_under_defense'] = _material_trace(
                        board, [item['move'], *last_defense['pv']])
                    _verify_defense(item, report['root'], board.in_check())
                    item['defense_need'] = _defense_need(item)
                    if offered:
                        reply = last_defense['pv'][0]
                        item['defense_accepts'] = reply[2:4] == item['move'][2:4]
                del defender

            if offered and item['iterations'] and not expired():
                score = item['iterations'][-1]['score'] * (1 if white_to_move else -1)
                plies = mate_plies(score)
                if score > 0 and plies is not None and plies <= VERIFY_MAX_PLY:
                    item['proof'] = mate_proof(board, item['move'], plies, deadline=deadline,
                                              cancel_check=cancelled)
                    if item['proof']['status'] == 'proved':
                        item['verification'] = 'mate_proved'
    report['outcome'] = ('cancelled' if cancelled() else 'completed' if report['root']
                         else 'no_completed_depth')
    publish('done')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fen', required=True)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--profile', choices=PROFILES, default='tactical')
    parser.add_argument('--candidate')
    parser.add_argument('--moves', nargs='+', default=(), help='Replay UCI moves from the supplied FEN.')
    parser.add_argument('--output', help='Write JSON to a file instead of stdout.')
    args = parser.parse_args()
    board = Board(args.fen)
    for move in args.moves:
        board.push_uci(move)
    report = analyze_deep(board, args.seconds, profile=args.profile, candidate=args.candidate)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as destination:
            destination.write(payload + '\n')
    else:
        print(payload)


if __name__ == '__main__':
    main()
