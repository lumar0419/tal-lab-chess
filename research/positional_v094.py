"""Isolated evaluation experiments, NOT enabled by the production engine.

Independent implementation: geometric mobility excludes friendly pieces and
enemy pawn attacks, not pins or other attacks. Development uses position only,
never move history (which would invalidate the board-keyed evaluation cache).
Weights are hypotheses until independent matches validate them.
"""
from contextlib import contextmanager

from board import SQUARES, EMPTY, OFF, WHITE, KNIGHT_STEPS, BISHOP_DIRS, ROOK_DIRS, QUEEN_DIRS, KING_STEPS, sq
import evaluate

NAMES = ('mobility_n_mg', 'mobility_n_eg', 'mobility_b_mg', 'mobility_b_eg',
         'mobility_r_mg', 'mobility_r_eg', 'mobility_q_mg', 'mobility_q_eg',
         'king_pressure_mg', 'king_shelter_mg', 'development_mg',
         'rook_file_mg', 'rook_file_eg')
INITIAL = (4, 3, 3, 3, 2, 3, 1, 2, 4, 8, 12, 8, 12)
GROUPS = {'mobility': tuple(range(8)), 'king': (8,9), 'development': (10,),
          'rook': (11,12), 'combined': tuple(range(13))}
DIRECTIONS = {'N':KNIGHT_STEPS, 'B':BISHOP_DIRS, 'R':ROOK_DIRS, 'Q':QUEEN_DIRS}


def features(board):
    """White-minus-Black integer features, already phase scaled (divisor 24)."""
    b=board.board
    pawns=([s for s in SQUARES if b[s]=='P'],[s for s in SQUARES if b[s]=='p'])
    guards=[set(),set()]
    for color in (0,1):
        step=10 if color==0 else -10
        for s in pawns[color]:
            for t in (s+step-1,s+step+1):
                if b[t]!=OFF: guards[color].add(t)
    phase=min(24,sum(evaluate.PHASE.get(b[s],0) for s in SQUARES))
    raw=[0]*13
    zones=[set(k+d for d in (0,)+KING_STEPS if b[k+d]!=OFF) for k in board.king_sq]
    for color in (0,1):
        sign=1 if color==0 else -1
        own='PNBRQK' if color==0 else 'pnbrqk'
        enemy_pawns=guards[color^1]
        files={s%10 for s in pawns[color]}
        enemy_files={s%10 for s in pawns[color^1]}
        attackers=pressure=0
        for s in SQUARES:
            p=b[s]
            if p not in own or p.upper() not in DIRECTIONS: continue
            kind=p.upper(); safe=hits=0
            for direction in DIRECTIONS[kind]:
                t=s+direction
                while b[t]!=OFF:
                    if b[t] in own: break
                    if t not in enemy_pawns: safe+=1
                    if t in zones[color^1]: hits+=1
                    if kind=='N' or b[t]!=EMPTY: break
                    t+=direction
            index='NBRQ'.index(kind)*2
            raw[index]+=sign*safe*phase
            raw[index+1]+=sign*safe*(24-phase)
            if hits:
                attackers+=1
                pressure+=min(hits,3)
            if kind=='R' and s%10 not in files:
                openness=1+(s%10 not in enemy_files)
                raw[11]+=sign*openness*phase
                raw[12]+=sign*openness*(24-phase)
        # Multiple attackers; queenless attacks count half. No sacrifice reward.
        queen='Q' if color==0 else 'q'
        if attackers>=2:
            raw[8]+=sign*min(12,pressure)*(2 if queen in b else 1)*phase
        k=board.king_sq[color]; step=10 if color==0 else -10
        # Shelter depends on actual pawns, not the PST's king-square bonus.
        if (k<41 if color==0 else k>78):
            pawn='P' if color==0 else 'p'
            shield=sum(b[k+step+d]==pawn for d in (-1,0,1))
            enemy_queen='q' if color==0 else 'Q'
            raw[9]+=sign*shield*phase*(enemy_queen in b)
        # Undeveloped home minors are a modest MG-only penalty. No repeated-
        # move counter: a FEN cannot tell whether a piece moved earlier.
        rank=0 if color==0 else 7
        minor='NB' if color==0 else 'nb'
        undeveloped=sum(b[sq(f,rank)]==p for f,p in zip((1,6,2,5),(minor[0],minor[0],minor[1],minor[1])))
        raw[10]-=sign*undeveloped*phase
    return raw


def score_white(board, weights):
    terms,phase,dead=evaluate.eval_terms(board)
    if dead: return 0
    numerator=sum(mg*phase+eg*(24-phase) for mg,eg in terms.values())
    numerator+=sum(x*w for x,w in zip(features(board),weights))
    return numerator//24 if numerator>=0 else -(-numerator//24)


@contextmanager
def candidate(weights):
    """Process-local research harness only. Fresh Searcher required per setting."""
    import search
    if len(weights)!=len(NAMES) or any(type(w) is not int for w in weights):
        raise ValueError('13 integer weights required')
    old=search.evaluate
    flags={k:getattr(evaluate,k) for k in ('KING_SAFETY','ATTACK_ACTIVITY','INITIATIVE')}
    try:
        for k in flags: setattr(evaluate,k,False)
        search.evaluate=lambda b: score_white(b,weights)*(1 if b.side==WHITE else -1)
        yield
    finally:
        search.evaluate=old
        for k,v in flags.items(): setattr(evaluate,k,v)


def group_weights(group, weights=INITIAL):
    active=GROUPS[group]
    return tuple(w if i in active else 0 for i,w in enumerate(weights))
