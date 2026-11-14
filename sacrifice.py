"""Conservative sacrifice *candidate* evidence; never changes engine evaluation.
A legal immediate capture of the offered non-pawn must leave a material loss
once Tal's legal static exchange evaluator accounts for recaptures. This is
not an exhaustive detector of delayed/positional sacrifices or brilliance.
"""
import time

from board import Board, WHITE
from search import MATE, MATE_BOUND, Searcher

VALUE={'P':100,'N':320,'B':330,'R':500,'Q':900,'K':0,'.':0,' ':0}

def balance(board, side):
    white=sum((1 if p.isupper() else -1)*VALUE[p.upper()] for p in board.board if p not in '. ')
    return white if side == WHITE else -white

def exchange_gain(board, move, budget=None, *, cancel_check=None):
    """Material gain of a forced capture and optimal optional recaptures.

    Legal moves exclude pinned/illegal king captures. This local exchange
    model ignores zwischenzugs; full search remains the tactical authority.
    """
    if budget is None: budget=[4000]
    if cancel_check and cancel_check():
        raise ProofInterrupted
    budget[0]-=1
    if budget[0]<0: raise ValueError("희생 교환 계산 한도 초과: 판정 보류")
    captured=VALUE[board.board[move.to].upper()]
    if board.board[move.frm].upper()=='P' and move.to==board.ep and not captured:
        captured=100
    promotion=VALUE[move.promo.upper()]-100 if move.promo else 0
    board.make_move(move)
    try:
        best=0
        for reply in board.legal_moves():
            if reply.to==move.to:
                best=max(best,exchange_gain(board,reply,budget,cancel_check=cancel_check))
        return captured+promotion-best
    finally:
        board.unmake_move()


def candidate_evidence(board, uci, *, cancel_check=None):
    move=board.parse_uci(uci)
    if move is None: raise ValueError('희생 후보는 현재 국면의 합법수여야 합니다.')
    return _offer_evidence(board, move, cancel_check)


def _offer_evidence(board, move, cancel_check=None):
    piece=board.board[move.frm]
    if piece.upper() in ('P','K') or move.promo: return None
    # Rebuild through snapshot so repetition and draw context are retained.
    b=Board(board.fen()); b.restore(board.snapshot()); side=b.side; before=balance(b,side)
    b.make_move(move)
    if b.outcome() is not None: return None
    replies=[]
    net_gain=balance(b,side)-before
    # Acceptance must be legal, including pinned pieces and king safety.
    for reply in b.legal_moves():
        if reply.to != move.to: continue
        # SEE is from the accepting opponent's perspective; subtract what the
        # offering move already gained. Positive residual means actual exposure.
        gain=exchange_gain(b,reply,cancel_check=cancel_check)
        loss=gain-net_gain
        if loss >= 100: replies.append({'uci':reply.uci(),'material_risk_cp':loss})
    if not replies: return None
    return {'move':move.uci(),'piece':piece,'acceptances':replies,'label':'희생 후보 · 검증 필요'}


class ProofInterrupted(Exception):
    pass


def mate_proof(board, uci, plies, *, node_budget=25000, deadline=None, cancel_check=None):
    """Prove mate within a bound. The attacker tries one move, the defender every move."""
    if type(plies) is not int or plies not in (1, 3, 5, 7):
        raise ValueError('Mate proof supports 1, 3, 5, or 7 plies.')
    view = Board(board.fen())
    view.restore(board.snapshot())
    attacker = view.side
    win = '1-0' if attacker == WHITE else '0-1'
    nodes = 0

    def prove(left):
        nonlocal nodes
        if (nodes >= node_budget or (deadline is not None and time.monotonic() >= deadline)
                or (cancel_check is not None and cancel_check())):
            raise ProofInterrupted
        nodes += 1
        outcome = view.outcome()
        if outcome is not None:
            return outcome[0] == win
        if left == 0:
            return False
        attack = view.side == attacker
        if not attack and view.claimable_draw():
            return False
        moves = view.legal_moves()
        if attack:
            moves.sort(key=lambda move: view.board[move.to] == '.')
        for reply in moves:
            view.make_move(reply)
            try:
                if not attack and view.claimable_draw():
                    outcome = view.outcome()
                    won = outcome is not None and outcome[0] == win
                else:
                    won = prove(left - 1)
            finally:
                view.unmake_move()
            if won == attack:
                return won
        return not attack

    if view.outcome() is not None:
        raise ValueError('이미 끝난 국면입니다.')
    view.push_uci(uci)
    try:
        status = 'proved' if prove(plies - 1) else 'not_forced_within_limit'
    except ProofInterrupted:
        status = 'incomplete'
    return {'status': status, 'max_plies': plies, 'nodes': nodes, 'node_budget': node_budget}

def analyze_candidate(board, uci, depth=4, seconds=5, *, cancel_check=None):
    deadline = time.monotonic() + seconds
    def cancelled():
        return time.monotonic() >= deadline or (cancel_check and cancel_check())

    try:
        evidence = candidate_evidence(board, uci, cancel_check=cancelled)
    except ProofInterrupted:
        return {'move': uci, 'status': 'incomplete', 'depth': 0, 'pv': []}
    if evidence is None: raise ValueError('즉시 수락 가능한 기물 희생 후보로 탐지되지 않았습니다.')
    return _verify_offer(board, evidence, depth, deadline, cancelled)


def _verify_offer(board, evidence, depth, deadline, cancel_check):
    move = evidence['move']
    child = Board(board.fen())
    child.restore(board.snapshot())
    child.push_uci(move)
    legal_count = len(child.legal_moves())
    report = {**evidence, 'status': 'incomplete', 'depth': 0, 'defense_depth': 0,
              'pv': [], 'defenses': [], 'legal_replies': legal_count, 'proof': None,
              'nodes': 0, 'seconds': 0}
    remaining = deadline - time.monotonic()
    if remaining <= 0 or (cancel_check and cancel_check()):
        return report
    searcher = Searcher(tt_size=60_000)
    searcher.qsearch_quiet_checks = True
    searcher.check_continuation = True
    groups = []
    searcher.search(child, max_depth=max(1, depth - 1), time_limit=remaining * 0.8,
                    full_time=True, multipv=3, on_info=None, on_multipv=groups.append,
                    cancel_check=cancel_check)
    report['nodes'] = searcher.nodes
    if not groups:
        return report
    offered_square = move[2:4]
    lines = []
    for info in groups[-1]:
        defense = info.pv[0].uci()
        attacker_score = -info.score
        if abs(attacker_score) > MATE_BOUND:
            attacker_score += -1 if attacker_score > 0 else 1
        score = attacker_score if board.side == WHITE else -attacker_score
        lines.append({'move': defense, 'attacker_score': attacker_score, 'score': score,
                      'response': 'accepts' if defense[2:4] == offered_square else 'declines',
                      'pv': [move, *(step.uci() for step in info.pv)]})
    first = lines[0]
    completed = groups[-1][0].depth
    claim_available = bool(child.claimable_draw() or searcher._can_announce_draw(child))
    score = first['score']
    if claim_available and first['attacker_score'] > 0:
        score = 0
    report.update(status='candidate', depth=completed+1, defense_depth=completed, score=score,
                  pv=first['pv'], best_defense=first['move'], defenses=lines,
                  defender_draw_claim=claim_available, seconds=groups[-1][-1].seconds,
                  warning='완료 깊이에서 평가한 방어 후보입니다.')
    mate_distance = MATE - first['attacker_score']
    if not claim_available and mate_distance in (1, 3, 5, 7):
        report['proof'] = mate_proof(board, move, mate_distance, deadline=deadline,
                                     cancel_check=cancel_check)
        if report['proof']['status'] == 'proved':
            report.update(status='verified_mate_sacrifice', label='강제 메이트 희생',
                          warning='표시한 반수 범위에서 상대의 모든 합법 방어를 검증했습니다.')
    return report


def discover_sacrifices(board, depth=6, seconds=5, *, cancel_check=None):
    """Screen every legal immediate offer, then verify a bounded shortlist."""
    deadline = time.monotonic() + seconds
    def cancelled():
        return time.monotonic() >= deadline or (cancel_check and cancel_check())

    offers = {}
    scan_complete = True
    for move in board.legal_moves() if board.outcome() is None else ():
        if cancelled():
            scan_complete = False
            break
        try:
            evidence = _offer_evidence(board, move, cancelled)
        except ProofInterrupted:
            scan_complete = False
            break
        except ValueError:  # Exchange branch exceeded the existing node budget.
            scan_complete = False
            continue
        if evidence:
            offers[move.uci()] = evidence
    report = {'offers_found': len(offers), 'scan_complete': scan_complete, 'ranked_depth': 0,
              'candidates': [], 'ranked_moves': []}
    remaining = deadline - time.monotonic()
    if not offers or remaining <= 0 or cancelled():
        return report
    groups = []
    searcher = Searcher(tt_size=60_000)
    searcher.qsearch_quiet_checks = True
    searcher.check_continuation = True
    searcher.search(board, max_depth=depth, time_limit=remaining * 0.60,
                    full_time=True, multipv=min(3, len(offers)), root_moves=offers,
                    on_info=None, on_multipv=groups.append, cancel_check=cancelled)
    if not groups:
        return report
    report['ranked_depth'] = groups[-1][0].depth
    report['ranked_moves'] = [line.pv[0].uci() for line in groups[-1]]
    for line in groups[-1][:2]:
        if cancelled():
            break
        move = line.pv[0].uci()
        now = time.monotonic()
        share = 0.6 if not report['candidates'] and len(groups[-1]) > 1 else 1
        candidate = _verify_offer(board, offers[move], depth, now + share * (deadline - now), cancelled)
        candidate['screening_score'] = line.score
        candidate['screening_depth'] = line.depth
        report['candidates'].append(candidate)
    return report
