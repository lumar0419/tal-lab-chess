"""
test_engine.py — 규칙 판정·탐색 정확성 테스트

  python test_engine.py          # 전체 (약 1~2분)

검증 항목
  [v0.3.1]  문제 1  정적 탐색의 체크 처리       문제 2  정적 탐색의 스테일메이트
            문제 3  체크메이트 점수의 일관성    ① 앙파상과 해시   ② 동형반복·50수 규칙·TT
            ③ 기물 부족   ④ 탐색 중단 후 상태 복구   ⑤ 비정상 입력   + 기존 기능 회귀 테스트 (78개)
  [v0.3.2]  5.1 Delta Pruning   5.2 무승부 청구·자동 무승부   5.3 종료 국면에서의 search()
            5.4 모든 탐색 전후 상태 유지   + play.py 실제 실행
  [v0.3.3]  A 나이트 승격 메이트  B 퀸 승격  C 잡으며 언더프로모션  D 스테일메이트 회피  E 흑 승격
            F Alpha-Beta 경계  G 상태 복구  + 추가 검토 ①~⑤, play.py 승격 입력

  python-chess(pip install chess)가 있으면 독립 라이브러리 교차 검증도 함 (없으면 '건너뜀', 통과로 세지 않음).
  엔진 자체는 python-chess가 필요 없음.
"""

import os
import random
import subprocess
import sys
import threading
import time

import search as search_mod
from board import Board, Move, START_FEN, EMPTY, WHITE, BLACK, parse_sq
from evaluate import evaluate, evaluate_white, mirror
from perft import perft, TESTS
from search import (Searcher, MATE, INF, MOVE_ONLY, format_score, uci_score,
                    _to_tt, _from_tt, TranspositionTable, EXACT, LOWER, UPPER)

RESULTS = []
GROUP = ['v0.3.1']          # 지금 실행 중인 테스트 묶음 (요약 출력용)


def check(name, cond, detail=''):
    RESULTS.append((GROUP[0], name, bool(cond)))
    mark = 'OK  ' if cond else '실패'
    print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ''))


def section(title):
    print(f"\n■ {title}")


def quiet_search(b, **kw):
    return Searcher().search(b, on_info=None, **kw)


class ks_mode:
    """with ks_mode(True/False): 그 안에서는 King Safety를 켠/끈 평가로 계산 (끝나면 원래 설정으로).
    테스트가 엔진의 기본 설정(켬/끔)에 좌우되지 않도록, 평가값을 비교하는 테스트는 설정을 직접 정함.
      끔 = v0.4.0까지의 평가. v0.3.x 테스트 중 평가값 자체를 고정값(+947, +9.00)으로 비교하는 것에 사용.
      켬 = King Safety 테스트에 사용."""
    def __init__(self, flag):
        self.flag = flag

    def __enter__(self):
        import evaluate
        self.old = evaluate.KING_SAFETY
        evaluate.KING_SAFETY = self.flag

    def __exit__(self, *exc):
        import evaluate
        evaluate.KING_SAFETY = self.old
        return False


def king_safety_off():
    return ks_mode(False)


def with_ks(flag):
    """테스트 함수 전체를 ks_mode(flag) 안에서 실행"""
    def deco(fn):
        def wrapped(*a, **kw):
            with ks_mode(flag):
                return fn(*a, **kw)
        wrapped.__name__ = fn.__name__
        return wrapped
    return deco


def random_positions(n_games, plies, seed, fens=None):
    """여러 출발 국면에서 무작위로 두며 국면들을 모음"""
    rng = random.Random(seed)
    fens = fens or [START_FEN] + [fen for _, fen, _ in TESTS]
    out = []
    for g in range(n_games):
        b = Board(fens[g % len(fens)])
        for _ in range(plies):
            moves = b.legal_moves()
            if not moves:
                break
            b.make_move(rng.choice(moves))
            out.append(b.fen())
    return out


# ───────────────────── 기준 구현: 정적 탐색을 '정의대로' 다시 짠 것 ─────────────────────
REF_VALUE = {'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9}


def _piece_counts(b):
    """기물 종류별 개수 (킹 제외). 수 전후를 비교해 잡기·승격을 알아내는 데 씀"""
    s = ''.join(b.board)
    return {c: s.count(c) for c in 'PNBRQpnbrq'}


def ref_quiesce(b, alpha, beta, ply):
    """search.quiesce와 독립적으로 작성한 기준 구현 (v0.3.3에서 다시 작성).

    정의: 체크면 모든 합법 회피 수, 아니면 stand pat + '전술적인 수'. 둘 수 없으면 메이트(-MATE+ply)/스테일메이트(0).
    '전술적인 수'를 엔진처럼 captures_only 생성기나 Move.promo 필드로 고르지 않고,
    합법수를 실제로 둔 뒤 기물 구성의 변화로 판정함 → 엔진의 후보 선택 코드와 오류를 공유하지 않음.
      · 상대 기물 수가 줄었으면 잡기 (앙파상 포함)
      · 내 폰 이외 기물이 늘었으면 승격 (일반 이동·캐슬링은 구성이 그대로) → 퀸·룩·비숍·나이트 4종 모두
    합법성 확인과 기물 변화 확인을 한 번의 두기로 함 (규칙 정확성은 perft로 검증된 전체 수 생성만 사용)."""
    in_check = b.in_check()
    if not in_check:
        stand = evaluate(b)
        if stand >= beta:                             # 멈춰도 되는 국면: 스테일메이트가 아닌지만 확인
            for m in b.pseudo_legal_moves():
                b.make_move(m)
                ok = not b.in_check(b.side ^ 1)
                b.unmake_move()
                if ok:
                    return stand
            return 0
    mine, theirs = ('PNBRQ', 'pnbrq') if b.side == WHITE else ('pnbrq', 'PNBRQ')
    before = _piece_counts(b)
    legal, scored = [], []
    for m in b.pseudo_legal_moves():
        b.make_move(m)
        if b.in_check(b.side ^ 1):                    # 둔 쪽 킹이 공격받으면 불법
            b.unmake_move()
            continue
        after = _piece_counts(b)
        b.unmake_move()
        legal.append(m)
        lost = [c for c in theirs if after[c] < before[c]]             # 상대 기물이 줄었음 = 잡기
        new = [c for c in mine[1:] if after[c] > before[c]]            # 내 폰 외 기물이 늘었음 = 승격
        if lost or new:
            # 순서는 결과값을 바꾸지 않음(전체 창 알파베타는 순서와 무관) → 속도만을 위한 정렬 키
            scored.append((sum(REF_VALUE[c.lower()] for c in lost) * 10
                           + sum(REF_VALUE[c.lower()] for c in new), m))
    if not legal:
        return -MATE + ply if in_check else 0
    if in_check:
        best, cand = -INF, legal
    else:
        best = stand
        alpha = max(alpha, best)
        scored.sort(key=lambda t: t[0], reverse=True)
        cand = [m for _, m in scored]
    for m in cand:
        b.make_move(m)
        score = -ref_quiesce(b, -beta, -alpha, ply + 1)
        b.unmake_move()
        if score > best:
            best = score
            alpha = max(alpha, score)
            if alpha >= beta:
                break
    return best


def engine_quiesce(fen, alpha=-INF, beta=INF, ply=0, delta=True, node_limit=None):
    """node_limit을 넘기면 None (트리가 너무 큰 국면은 비교에서 제외하려고)"""
    s = Searcher()
    s.delta_pruning = delta
    s.node_limit = node_limit
    try:
        return s.quiesce(Board(fen), alpha, beta, ply)
    except search_mod.TimeUp:
        return None


def engine_negamax(fen, depth, ply=0):
    return Searcher().negamax(Board(fen), depth, -INF, INF, ply)


# ───────────────────── 기준 구현: 메이트 거리 완전 탐색 ─────────────────────
def mates_within(b, n):
    """둘 차례인 쪽이 n수(자기 수 기준) 안에 강제로 메이트시킬 수 있는가"""
    if n <= 0:
        return False
    for m in b.legal_moves():
        b.make_move(m)
        ok = gets_mated_within(b, n - 1)
        b.unmake_move()
        if ok:
            return True
    return False


def gets_mated_within(b, n):
    """둘 차례인 쪽이 무엇을 두어도 상대의 n수 안에 메이트당하는가 (n=0: 지금 메이트 상태)"""
    moves = b.legal_moves()
    if not moves:
        return b.in_check()
    for m in moves:
        b.make_move(m)
        ok = mates_within(b, n)
        b.unmake_move()
        if not ok:
            return False
    return True


def min_mate(b, limit):
    """둘 차례인 쪽의 최단 강제 메이트 수 (limit 이하에서 없으면 None)"""
    for n in range(1, limit + 1):
        if mates_within(b, n):
            return n
    return None


def random_kxk(rng, piece):
    """백 킹 + piece 대 흑 킹 무작위 국면 (백 차례, 합법 국면만).
    메이트가 나오기 쉬운 배치로 치우치게 뽑음: 흑 킹은 가장자리, 백 킹은 흑 킹에서 두 칸 거리."""
    edge = [c for c in range(64) if c % 8 in (0, 7) or c // 8 in (0, 7)]
    while True:
        bk = rng.choice(edge)
        near = [c for c in range(64)
                if max(abs(c % 8 - bk % 8), abs(c // 8 - bk // 8)) == 2]
        wk = rng.choice(near)
        pc = rng.choice([c for c in range(64) if c not in (bk, wk)])
        cells = [wk, pc, bk]
        board = ['.'] * 64
        for c, p in zip(cells, ('K', piece, 'k')):
            board[c] = p
        rows = []
        for r in range(7, -1, -1):
            row, e = '', 0
            for f in range(8):
                p = board[r * 8 + f]
                if p == '.':
                    e += 1
                else:
                    row += (str(e) if e else '') + p
                    e = 0
            rows.append(row + (str(e) if e else ''))
        try:
            b = Board('/'.join(rows) + ' w - - 0 1')
        except ValueError:
            continue
        if not b.in_check() and b.outcome() is None:
            return b


# ═══════════════════════════════════ 테스트 ═══════════════════════════════════
def test_problem1_check_in_quiescence():
    section("문제 1. 정적 탐색에서 체크 상태 처리")
    fork = "q3k3/2N5/8/8/8/8/4P3/4K3 b - - 0 1"   # 나이트가 킹 체크 + 퀸 포크, 흑 차례
    v = engine_quiesce(fork)
    check("체크 상태에서는 stand pat(평가값)을 쓰지 않음",
          v != evaluate(Board(fork)) and v < 0,
          f"평가값 {evaluate(Board(fork)):+d} → 정적 탐색 {v:+d} (흑이 퀸을 잃는 게 반영됨)")
    check("기준 구현과 같은 값", v == ref_quiesce(Board(fork), -INF, INF, 0))
    lone = "q3k3/2N5/8/8/8/8/8/4K3 b - - 0 1"     # 폰이 없으면 퀸을 잃어도 킹+나이트 대 킹 → 무승부
    check("같은 포크에서 백 폰이 없으면 0점 (퀸을 잡은 뒤 기물 부족 무승부)", engine_quiesce(lone) == 0)

    mate_by_capture = "7k/6pp/8/7N/8/8/8/6QK w - - 0 1"   # Qxg7# (잡으면서 메이트)
    check("정적 탐색 안에서 일어나는 메이트도 찾음 (Qxg7#)",
          engine_quiesce(mate_by_capture) == MATE - 1,
          f"{engine_quiesce(mate_by_capture)} == MATE-1")

    # 무작위 국면(체크 국면 위주)에서 엔진 정적 탐색 == 기준 구현 (델타 가지치기만 끔)
    fens = random_positions(60, 40, seed=7)
    in_check = [f for f in fens if Board(f).in_check()]
    normal = [f for f in fens if not Board(f).in_check()][::25]
    mismatch = compared = 0
    small_check = []
    for f in in_check + normal:
        f0 = ' '.join(f.split()[:4]) + ' 0 1'      # 반복·50수 영향 제거
        e = engine_quiesce(f0, delta=False, node_limit=3000)
        if e is None:
            continue                               # 트리가 큰 국면은 기준 구현이 너무 느려 제외
        compared += 1
        if f in in_check:
            small_check.append(f0)
        r = ref_quiesce(Board(f0), -INF, INF, 0)
        if e != r:
            mismatch += 1
            print("    불일치:", f0, e, r)
    check(f"무작위 국면 {compared}개 (체크 국면 {len(small_check)}개)에서 기준 구현과 일치",
          mismatch == 0 and len(small_check) >= 30, f"불일치 {mismatch}개")

    # 좁은 창(alpha, beta)에서도 알파베타 경계가 맞는지: 값 v 기준으로 fail-high/low 방향 확인
    ok = True
    for f0 in small_check[:40]:
        exact = engine_quiesce(f0, delta=False)
        for a, bb in ((exact - 50, exact + 50), (exact + 1, exact + 100), (exact - 100, exact - 1)):
            got = engine_quiesce(f0, a, bb, delta=False)
            if a < exact < bb and got != exact:
                ok = False
            if exact <= a and got > a:
                ok = False
            if exact >= bb and got < bb:
                ok = False
    check("체크 국면에서 좁은 탐색 창(alpha-beta 경계)도 정확", ok)


def test_problem2_stalemate_in_quiescence():
    section("문제 2. 정적 탐색의 스테일메이트")
    stale = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    b = Board(stale)
    check("board.outcome() = 스테일메이트", b.outcome() == ('1/2-1/2', '스테일메이트'), str(b.outcome()))
    for a, bb, label in ((-INF, INF, "전체 창"), (-2000, -1000, "stand pat ≥ beta 로 컷되는 창"),
                         (100, 200, "stand pat < alpha 인 창")):
        v = engine_quiesce(stale, a, bb)
        check(f"quiesce = 0 ({label})", v == 0, f"{v}")
    check("negamax 깊이 1~3 = 0", all(engine_negamax(stale, d) == 0 for d in (1, 2, 3)))
    check("search() → (None, 0)", quiet_search(Board(stale), max_depth=3) == (None, 0))
    check("색을 뒤바꾼 국면도 0", engine_quiesce(mirror(Board(stale)).fen()) == 0)

    trap = "7k/5K1p/7P/8/8/1N6/2PP4/b7 w - - 0 1"   # Nxa1 하면 흑 스테일메이트
    b = Board(trap)
    b.push_uci('b3a1')
    check("함정 수 Nxa1 직후 정적 탐색 = 0 (이전 코드는 흑 기준 -5.20점)",
          engine_quiesce(b.fen()) == 0, f"{engine_quiesce(b.fen())}")
    picks = [quiet_search(Board(trap), max_depth=d)[0].uci() for d in (1, 2, 3, 4)]
    check("깊이 1~4 어디서도 Nxa1(b3a1)을 두지 않음", 'b3a1' not in picks, ' '.join(picks))


def test_problem3_mate_scores():
    section("문제 3. 체크메이트 점수의 일관성")
    mated = "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"
    b = Board(mated)
    check("board.outcome() = 1-0 체크메이트", b.outcome() == ('1-0', '체크메이트'), str(b.outcome()))
    check("negamax(루트) = -MATE (깊이 1~3)", all(engine_negamax(mated, d) == -MATE for d in (1, 2, 3)))
    check("quiesce(루트) = -MATE", engine_quiesce(mated) == -MATE)
    check("ply 5에서 만나면 -MATE+5 (negamax·quiesce 동일)",
          engine_negamax(mated, 2, ply=5) == -MATE + 5 and engine_quiesce(mated, ply=5) == -MATE + 5)
    check("search() → (None, -MATE), 표기 '#0' / 'mate 0'",
          quiet_search(Board(mated), max_depth=2) == (None, -MATE)
          and format_score(-MATE) == '#0' and uci_score(-MATE) == 'mate 0')

    # 부호와 거리
    m1 = "7k/8/6K1/8/8/8/8/R7 w - - 0 1"            # Ra8#
    mv, sc = quiet_search(Board(m1), max_depth=4)
    check("1수 메이트: 점수 MATE-1, '#1', Ra8", sc == MATE - 1 and format_score(sc) == '#1' and mv.uci() == 'a1a8')
    m2 = "3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1"
    s = Searcher()
    infos = []
    mv, sc = s.search(Board(m2), max_depth=6, on_info=infos.append)
    pv = infos[-1].pv
    bb = Board(m2)
    for m in pv:
        bb.make_move(m)
    check("2수 메이트: 점수 MATE-3, '#2', 수순 3수(ply)가 체크메이트로 끝남",
          sc == MATE - 3 and format_score(sc) == '#2' and len(pv) == 3 and bb.outcome()[1] == '체크메이트',
          ' '.join(m.uci() for m in pv))
    bb = Board(m2)
    bb.push_uci('e2e8')
    check("지는 쪽 점수: 1.Re8+ 이후 흑 차례 → MATE 거리 2 → -(MATE-2), '#-1'",
          quiet_search(bb, max_depth=4)[1] == -(MATE - 2) and format_score(-(MATE - 2)) == '#-1')

    # 가장 빠른 메이트 선호 / 최대한 늦게 메이트당하기 — 완전 탐색과 대조
    rng = random.Random(11)
    fast_ok = fast_n = 0
    while fast_n < 12:
        b = random_kxk(rng, rng.choice('QR'))
        n = min_mate(b, 2)
        if n is None:
            continue
        fast_n += 1
        mv, sc = quiet_search(b, max_depth=5)
        b.make_move(mv)
        achieves = gets_mated_within(b, n - 1)
        fast_ok += (sc == MATE - (2 * n - 1)) and achieves
    check("가장 빠른 메이트를 고름 (무작위 KQK/KRK 12국면, 완전 탐색과 대조)", fast_ok == fast_n,
          f"{fast_ok}/{fast_n}")

    slow_ok = slow_n = 0
    tries = 0
    while slow_n < 8 and tries < 3000:
        tries += 1
        w = random_kxk(rng, 'Q')
        moves = w.legal_moves()
        w.make_move(rng.choice(moves))
        if w.outcome() is not None:
            continue
        # 흑 차례: 각 수 뒤 백의 최단 메이트 거리 (2수 넘으면 99로 취급)
        dist = {}
        for m in w.legal_moves():
            w.make_move(m)
            dist[m.uci()] = min_mate(w, 2) or 99
            w.unmake_move()
        if len(set(dist.values())) < 2 or max(dist.values()) == 99:
            continue                 # 수마다 거리가 다르고, 모두 2수 안에 메이트당하는 국면만
        slow_n += 1
        mv, sc = quiet_search(w, max_depth=6)
        best = max(dist.values())
        slow_ok += dist[mv.uci()] == best and sc == -(MATE - 2 * best)
    check("질 수밖에 없으면 가장 늦게 메이트당하는 수를 고름 (8국면, 완전 탐색과 대조)",
          slow_ok == slow_n and slow_n > 0, f"{slow_ok}/{slow_n}")

    # TT 저장·복원
    ok = all(_from_tt(_to_tt(sv, p), p) == sv for p in range(0, 40)
             for sv in (MATE - 3, MATE - 50, -(MATE - 4), -(MATE - 60), 0, 250, -999))
    # 노드에서 d수 뒤 메이트: ply p1에서 저장 → ply p2에서 꺼내면 '루트에서 p2+d'
    ok &= all(_from_tt(_to_tt(MATE - (p1 + d), p1), p2) == MATE - (p2 + d)
              for p1 in range(10) for p2 in range(10) for d in range(1, 8))
    ok &= all(_from_tt(_to_tt(-(MATE - (p1 + d)), p1), p2) == -(MATE - (p2 + d))
              for p1 in range(10) for p2 in range(10) for d in range(0, 8))
    check("_to_tt/_from_tt: 왕복 일치, 다른 ply로 옮겨도 메이트 거리 보존", ok)

    s = Searcher()
    s.search(Board(m2), max_depth=6, on_info=None)
    after = Board(m2)
    after.push_uci('e2e8')
    warm = s.search(after, max_depth=4, on_info=None)[1]
    cold = Searcher().search(after, max_depth=4, on_info=None)[1]
    again = s.search(Board(m2), max_depth=6, on_info=None)[1]
    check("TT가 차 있는 상태(warm)와 빈 상태(cold)의 메이트 점수가 같음",
          warm == cold == -(MATE - 2) and again == MATE - 3, f"warm {warm}, cold {cold}")


def test_ep_hash():
    section("① Zobrist 해시와 앙파상")
    b = Board()
    b.push_uci('e2e4')
    same = Board('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1')
    check("1.e4 직후(잡을 흑 폰 없음): 앙파상 칸이 없는 국면과 같은 해시, FEN에는 e3 유지",
          b.hash == same.hash and ' e3 ' in b.fen())

    real = Board('rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 3')
    no_ep = Board('rnbqkbnr/ppp1pppp/8/8/3pP3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 3')
    check("실제로 앙파상 가능(d4xe3): 해시가 다름, 합법수에 d4e3 있음",
          real.hash != no_ep.hash and 'd4e3' in [m.uci() for m in real.legal_moves()])

    pinned = Board('8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 b - - 0 1')
    pinned.push_uci('c7c5')
    no_ep = Board('8/8/3p4/KPp4r/1R3p1k/8/4P1P1/8 w - - 0 2')
    legal = [m.uci() for m in pinned.legal_moves()]
    check("앙파상 자리는 있지만 핀 때문에 불법(b5xc6): 앙파상 없는 국면과 같은 해시",
          pinned.hash == no_ep.hash and 'b5c6' not in legal)

    b = Board()
    for mv in "e2e4 g8f6 g1f3 f6g8 f3g1 g8f6 g1f3 f6g8 f3g1".split():
        b.push_uci(mv)
    check("1.e4 직후 국면이 기사 왕복으로 3번째 등장 → 3회 동형반복 청구 가능 (이전 코드: 2회로 셈)",
          b.repetition_count() == 3 and b.claimable_draw() == '3회 동형반복')

    b = Board()
    for mv in "e2e4 b8c6 e4e5 d7d5 g1f3 c6b8 f3g1 b8c6 g1f3 c6b8 f3g1 b8c6".split():
        b.push_uci(mv)
    check("앙파상이 실제로 가능했던 첫 국면은 다른 국면으로 셈 (2회)",
          b.repetition_count() == 2 and b.claimable_draw() is None, f"{b.repetition_count()}회")

    bad = 0
    n = 0
    rng = random.Random(5)
    for g in range(150):
        b = Board([START_FEN, TESTS[1][1], TESTS[2][1]][g % 3])
        for _ in range(60):
            moves = b.legal_moves()
            if not moves:
                break
            pawn_doubles = [m for m in moves if b.board[m.frm] in 'Pp' and abs(m.to - m.frm) == 20]
            m = rng.choice(pawn_doubles) if pawn_doubles and rng.random() < 0.5 else rng.choice(moves)
            b.make_move(m)
            n += 1
            bad += b.hash != b.compute_hash()
        while b.history:
            b.unmake_move()
            bad += b.hash != b.compute_hash()
    check(f"두 칸 전진을 자주 섞은 무작위 대국 {n}수: 차분 갱신 해시 == 처음부터 계산 (두기·되돌리기 모두)",
          bad == 0, f"불일치 {bad}")


def test_repetition_fifty():
    section("② 동형반복·50수 규칙과 TT")
    b = Board()
    cycle = "g1f3 g8f6 f3g1 f6g8".split()
    for mv in cycle * 2:
        b.push_uci(mv)
    check("3회 동형반복: 청구 가능, 자동 종료는 아님",
          b.repetition_count() == 3 and b.claimable_draw() == '3회 동형반복' and b.outcome() is None)
    for mv in cycle * 2:
        b.push_uci(mv)
    check("5회 동형반복: 자동 무승부", b.outcome() == ('1/2-1/2', '5회 동형반복'))

    b = Board('8/8/8/4k3/8/8/8/R3K3 w - - 99 100')
    b.push_uci('a1a2')
    check("50수 규칙: halfmove 100 → 청구 가능, 자동 종료는 아님",
          b.claimable_draw() == '50수 규칙' and b.outcome() is None)
    b = Board('8/8/8/4k3/8/8/8/R3K3 w - - 149 100')
    b.push_uci('a1a2')
    check("75수 규칙: halfmove 150 → 자동 무승부", b.outcome() == ('1/2-1/2', '75수 규칙'))

    for hm, rule in ((99, '50수'), (149, '75수')):
        b = Board(f'7k/8/6K1/8/8/8/8/R7 w - - {hm} 80')
        mv, sc = quiet_search(Board(b.fen()), max_depth=4)
        b.push_uci('a1a8')
        check(f"{rule}째 수가 메이트(Ra8#)면 메이트 우선: outcome·탐색 모두 메이트",
              b.outcome() == ('1-0', '체크메이트') and mv.uci() == 'a1a8' and sc == MATE - 1,
              f"탐색 {mv.uci()} {format_score(sc)} (이전 코드: a1a2 +0.00)")

    # 탐색용 반복 판정: 트리 안 2회 vs 루트 이전 기록 3회
    s = Searcher()
    b = Board()
    for mv in cycle:
        b.push_uci(mv)                        # 시작 국면 2번째 (기록상)
    s.root_len = len(b.history)
    r1 = s._is_repetition_draw(b)
    for mv in cycle:
        b.push_uci(mv)                        # 루트 이후(트리 안)에서 다시 등장
    r2 = s._is_repetition_draw(b)
    s.root_len = len(b.history)               # 이제 루트 이전에 2번 등장한 상태
    b2 = Board()
    for mv in cycle * 2:
        b2.push_uci(mv)
    s2 = Searcher()
    s2.root_len = 4
    r3 = s2._is_repetition_draw(b2)           # 루트 이전 1번 + 트리 안 → 무승부
    s2.root_len = 8
    r3b = s2._is_repetition_draw(b2)          # 루트 이전 2번(지금이 3번째) → 무승부
    s2.root_len = 8
    b3 = Board()
    for mv in cycle:
        b3.push_uci(mv)
    s3 = Searcher()
    s3.root_len = 4
    check("탐색용 반복: 루트 이전에 1번 나온 국면은 무승부 아님 / 트리 안 반복은 무승부 / 3번째는 무승부",
          r1 is False and r2 is True and r3 is True and r3b is True and s3._is_repetition_draw(b3) is False)

    # 지는 쪽이 3회 반복으로 비기기 + 이력 의존 점수를 TT에 저장하지 않음
    b = Board('4k3/8/8/8/8/8/8/R3K3 w - - 0 1')
    for mv in "e1d1 e8d7 d1e1 d7e8 e1d1 e8d7 d1e1".split():
        b.push_uci(mv)                        # 흑 차례: Ke8 이면 시작 국면 3번째
    s = Searcher()
    mv, sc = s.search(b, max_depth=4, on_info=None)
    entry = s.tt.get(b.hash)
    check("룩이 없는 흑이 3회 반복 수(Ke8)로 비김을 선택, 점수 0",
          mv.uci() == 'd7e8' and sc == 0, f"{mv.uci()} {format_score(sc)}")
    check("그 국면의 TT에는 점수가 아닌 '수 정렬용 최선수'만 저장 (이력 의존 결과)",
          entry is not None and entry[1] == MOVE_ONLY, f"{entry}")
    s.root_len = 0                     # 이력 없는 같은 국면을 트리 안(ply 1)에서 만난 상황
    inner_warm = s.negamax(Board(b.fen()), 4, -INF, INF, 1)
    inner_cold = Searcher().negamax(Board(b.fen()), 4, -INF, INF, 1)
    check("이력 없는 같은 국면을 트리 안(ply 1)에서 만나도 TT의 반복 무승부 0점을 재사용하지 않음",
          inner_warm == inner_cold and inner_warm < -300, f"warm {inner_warm}, cold {inner_cold}")
    warm = s.search(Board(b.fen()), max_depth=4, on_info=None)[1]
    cold = Searcher().search(Board(b.fen()), max_depth=4, on_info=None)[1]
    check("같은 국면을 이력 없이 루트에서 다시 탐색해도 원래(지는) 점수",
          warm == cold and warm < -300, f"warm {warm}, cold {cold}")

    # 50수 규칙과 TT: halfmove 0에서 쌓은 TT를 halfmove 98 국면에 잘못 쓰지 않는지
    # (처음 탐색은 깊이 3 → 4수 미만이라 반복이 생길 수 없어 모든 노드의 점수가 TT에 저장됨)
    for d1, d2 in ((3, 2), (3, 3), (5, 3)):
        s = Searcher()
        s.search(Board('8/8/8/4k3/8/8/8/R3K3 w - - 0 1'), max_depth=d1, on_info=None)
        warm = s.search(Board('8/8/8/4k3/8/8/8/R3K3 w - - 98 100'), max_depth=d2, on_info=None)[1]
        cold = Searcher().search(Board('8/8/8/4k3/8/8/8/R3K3 w - - 98 100'), max_depth=d2, on_info=None)[1]
        check(f"halfmove 98 국면: halfmove 0에서 채운 TT(깊이 {d1})가 있어도 50수 무승부(0점)를 정확히 봄",
              warm == cold == 0, f"warm {warm}, cold {cold}")


def test_insufficient_material():
    section("③ 기물 부족")
    cases = [
        ("4k3/8/8/8/8/8/8/4K3 w - - 0 1", True, "킹 대 킹"),
        ("4k3/8/8/8/8/8/8/4KN2 w - - 0 1", True, "킹+나이트 대 킹"),
        ("4k3/8/8/8/8/8/8/4KB2 w - - 0 1", True, "킹+비숍 대 킹"),
        ("4k3/8/8/8/2b5/8/8/4KB2 w - - 0 1", True, "비숍 대 비숍, 같은 색 칸"),
        ("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1", False, "같은 편 비숍 2개, 다른 색 칸"),
        ("4k3/8/8/8/8/8/8/1B1BK3 w - - 0 1", True, "같은 편 비숍 2개, 같은 색 칸"),
        ("4k3/8/8/8/3b4/8/8/4KB2 w - - 0 1", False, "비숍 대 비숍, 다른 색 칸"),
        ("4k3/8/8/8/8/8/8/3NKN2 w - - 0 1", False, "킹+나이트 2개 대 킹"),
        ("4k1n1/8/8/8/8/8/8/4KN2 w - - 0 1", False, "나이트 대 나이트"),
        ("4k1n1/8/8/8/8/8/8/4KB2 w - - 0 1", False, "비숍 대 나이트"),
        ("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", False, "킹+폰 대 킹"),
        ("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", False, "킹+룩 대 킹"),
    ]
    for fen, dead, name in cases:
        b = Board(fen)
        got = b.insufficient_material()
        oc = b.outcome()
        eval_ok = (evaluate(b) == 0) if dead else True
        check(f"{name}: {'죽은 국면' if dead else '죽은 국면 아님'}",
              got == dead and ((oc is not None) == dead) and eval_ok,
              f"outcome={oc}, 평가={evaluate(b)}")
    check("킹+룩 대 킹은 평가가 0이 아님 (이기는 쪽으로 봄)", evaluate(Board(cases[-1][0])) > 300)


def test_search_interruption():
    section("④ 탐색 중단과 상태 복구")
    base = Board(TESTS[1][1])
    for mv in ['e1g1', 'e8c8', 'd5e6', 'a6e2']:   # 대국 기록이 있는 상태에서 시작
        base.push_uci(mv)
    fen0, snap0 = base.fen(), base.snapshot()

    ok = True
    for limit in (1, 2, 3, 7, 31, 100, 523, 2000, 7001):
        mv, sc = Searcher().search(base, node_limit=limit, on_info=None)
        ok &= base.snapshot() == snap0 and mv in base.legal_moves()
    check("노드 한도 9가지로 끊어도 보드·차례·캐슬링·앙파상·halfmove/fullmove·해시·기록 모두 복구, 합법수 반환",
          ok)

    mv, _ = Searcher().search(base, time_limit=0.0005, on_info=None)
    check("시간 한도 0.5ms로 끊어도 복구 + 합법수 반환", base.snapshot() == snap0 and mv in base.legal_moves())

    s = Searcher()
    threading.Timer(0.3, lambda: setattr(s, 'stop_requested', True)).start()
    t0 = time.time()
    mv, _ = s.search(base, on_info=None)              # 한도 없음 → 다른 스레드의 정지 요청으로만 끝남
    check("다른 스레드의 정지 요청(stop)으로 끊어도 복구", base.snapshot() == snap0
          and mv in base.legal_moves() and time.time() - t0 < 2, f"{time.time() - t0:.2f}s 만에 정지")

    original = search_mod.evaluate
    for exc in (RuntimeError, KeyboardInterrupt):
        calls = [0]

        def boom(b, _exc=exc):
            calls[0] += 1
            if calls[0] > 300:
                raise _exc("탐색 중 강제 예외")
            return original(b)

        search_mod.evaluate = boom
        raised = False
        try:
            Searcher().search(base, max_depth=6, on_info=None)
        except exc:
            raised = True
        finally:
            search_mod.evaluate = original
        check(f"탐색 중 {exc.__name__} 발생: 예외는 그대로 전달되고 국면은 복구", raised and base.snapshot() == snap0
              and base.fen() == fen0 and base.hash == base.compute_hash())
    check("복구된 국면으로 perft(2)가 새 보드와 같음", perft(base, 2) == perft(Board(base.fen()), 2))
    while base.history:
        base.unmake_move()
    check("기록을 끝까지 되돌리면 원래 출발 FEN", base.fen() == TESTS[1][1])


def test_abnormal_input():
    section("⑤ 비정상 국면·입력")
    bad_fens = [
        ("8/8/8/8/8/8/8/4K3 w - - 0 1", "흑 킹 없음"),
        ("4k3/8/8/8/8/8/8/3KK3 w - - 0 1", "백 킹 2개"),
        ("4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1", "둘 차례가 아닌 흑이 체크 상태"),
        ("P3k3/8/8/8/8/8/8/4K3 w - - 0 1", "8랭크에 폰"),
        ("4k3/8/8/8/8/8/8/4K3 x - - 0 1", "차례 표기 오류"),
        ("4k3/8/8/9/8/8/8/4K3 w - - 0 1", "랭크 칸 수 오류"),
        ("4k3/8/8/8/8/8/4K3 w - - 0 1", "랭크 7개"),
        ("4k3/8/8/8/8/8/8/4KX2 w - - 0 1", "알 수 없는 기물"),
        ("4k3/8/8/8/8/8/8/4K3 w - - -3 1", "음수 halfmove"),
        ("", "빈 문자열"),
    ]
    b = Board(TESTS[1][1])
    snap = b.snapshot()
    all_raise = True
    for fen, name in bad_fens:
        try:
            Board(fen)
            all_raise = False
            print("    예외가 안 남:", name)
        except ValueError:
            pass
        try:
            b.set_fen(fen)
            all_raise = False
        except ValueError:
            pass
    check("잘못된 FEN 10종 모두 ValueError (킹 개수, 반대편 체크, 폰 위치, 형식 오류 등)", all_raise)
    check("set_fen이 실패해도 기존 국면은 그대로", b.snapshot() == snap)

    b = Board('4k3/8/8/8/8/8/8/4K2R w KQkq - 0 1')
    check("캐슬링 권리 보정: 룩·킹이 제자리에 없는 권리는 버림 (KQkq → K)", b.fen().split()[2] == 'K')
    b = Board('4k3/8/8/8/8/8/8/4K3 w - e6 0 1')
    check("앙파상 칸 보정: 두 칸 전진한 폰이 없으면 버림", b.ep == 0 and b.fen().split()[3] == '-')

    kings_hit = 0
    for f in random_positions(40, 50, seed=21):
        bb = Board(f)
        kings_hit += sum(bb.board[m.to] in 'Kk' for m in bb.pseudo_legal_moves())
        kings_hit += sum(bb.board[m.to] in 'Kk' for m in bb.pseudo_legal_moves(captures_only=True))
    check("무작위 국면 약 2000개에서 킹을 잡는 수가 한 번도 생성되지 않음", kings_hit == 0)

    b = Board()
    snap = b.snapshot()
    junk = ['', 'e2', 'e2e5', 'z9z9', 'e7e5', None, 12, 'e2e4qq', ' E2E4 ']
    parsed = [b.parse_uci(x) for x in junk]
    check("이상한 수 입력은 None (단, ' E2E4 '처럼 공백·대문자만 다른 건 허용)",
          parsed[:-1] == [None] * (len(junk) - 1) and parsed[-1] is not None)
    try:
        b.push_uci('e2e5')
        pushed = True
    except ValueError:
        pushed = False
    check("불법수 push_uci → ValueError, 국면 그대로", not pushed and b.snapshot() == snap)
    try:
        b.make_move(Move(parse_sq('e4'), parse_sq('e5')))   # 빈 칸에서 출발하는 수
        made = True
    except KeyError:
        made = False
    check("make_move에 빈 칸 출발 수를 넣으면 예외, 국면은 손상되지 않음", not made and b.snapshot() == snap)


def test_regression():
    section("회귀 테스트 (기존 기능)")
    ok = True
    for _, fen, expected in TESTS:
        for depth, answer in expected.items():
            if answer <= 100_000:
                ok &= perft(Board(fen), depth) == answer
    check("perft 정답 (6개 국면, 노드 10만 이하 깊이 전부)", ok)

    bad = 0
    for f in random_positions(40, 40, seed=3):
        b = Board(f)
        bad += evaluate_white(b) != -evaluate_white(mirror(b))
    check("평가함수 대칭 (무작위 국면 1600개)", bad == 0, f"비대칭 {bad}")

    errors = 0
    results = []
    for g in range(2):
        b = Board()
        engines = [Searcher(), Searcher()]
        while b.outcome() is None and len(b.history) < 200:
            mv, _ = engines[b.side].search(b, time_limit=0.05, on_info=None)
            if mv not in b.legal_moves():
                errors += 1
                break
            b.make_move(mv)
            errors += b.hash != b.compute_hash()
        results.append(b.outcome() or ('…', '200수 제한'))
    check("엔진끼리 2판 자체 대국: 불법수·해시 불일치 없음", errors == 0, f"결과 {results}")


# ═══════════════════════════════ v0.3.2 추가 테스트 ═══════════════════════════════
def classify(r, v, a, b):
    """정확값 v를 기준으로, 창 (a, b)에서 받은 fail-soft 반환값 r을 판정.
      'exact'  창 안: r == v
      'bound'  창 밖: fail-low면 v ≤ r ≤ a (올바른 상한), fail-high면 b ≤ r ≤ v (올바른 하한)
      'error'  그 외 (틀린 값이거나, 상·하한이 거짓)"""
    if a < v < b:
        return 'exact' if r == v else 'error'
    if v <= a:
        return ('exact' if r == v else 'bound') if v <= r <= a else 'error'
    return ('exact' if r == v else 'bound') if b <= r <= v else 'error'


def windows_around(v):
    return [(-INF, INF), (2000, 4000), (-4000, -2000), (v - 1, v + 1), (v - 100, v - 1),
            (v + 1, v + 100), (-INF, v - 1), (v + 1, INF), (-1, 1), (500, 600)]


def search_keeps_state(b, **kw):
    """요구사항 5.4 그대로: 탐색 전후 FEN·해시·기록 길이가 같은지 확인하며 탐색"""
    original_fen, original_hash, original_len = b.fen(), b.hash, len(b.history)
    s = kw.pop('searcher', None) or Searcher()
    move, score = s.search(b, on_info=None, **kw)
    same = b.fen() == original_fen and b.hash == original_hash and len(b.history) == original_len
    return move, score, same


def test_v032_delta_pruning():
    section("v0.3.2-5.1  Delta Pruning")
    cases = [
        ("7k/6pp/8/7N/8/8/8/6QK w - - 0 1", "체크를 주는 잡기로 1수 메이트 (Qxg7#)", MATE - 1),
        ("3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1", "잡기만으로 2수 메이트 (Rxe8+ Qxe8 Rxe8#)", MATE - 3),
        ("6k1/5ppp/8/8/8/8/1p3PPP/6K1 b - - 0 1", "승격으로 1수 메이트 (b1=Q#)", MATE - 1),
        ("q3k3/2N5/8/8/8/8/4P3/4K3 b - - 0 1", "체크 상태에서 회피 (포크)", None),
        ("rnbqkbnr/pp3ppp/2p5/3p4/8/8/PPP2PPP/RNBQKBNR w KQkq - 0 4", "체크 아닌 일반 잡기 (Qxd5?)", None),
        ("8/4P3/8/8/8/8/k7/4K3 w - - 0 1", "체크 아닌 승격 (e8=Q)", None),
    ]
    a, bb = 2000, 4000
    v = Searcher().quiesce(Board(cases[0][0]), a, bb, 0)
    s_old = Searcher()
    s_old.delta_pruning = True
    with king_safety_off():                   # +947은 v0.4.0까지의 평가로 나온 값
        v_old = s_old.quiesce(Board(cases[0][0]), a, bb, 0)
    check("요구 국면 Qxg7#, 창(2000, 4000): 기본값(Delta 끔)은 +99999로 fail-high(올바른 하한)",
          v == MATE - 1 and classify(v, MATE - 1, a, bb) != 'error', f"{v:+d}")
    check("재현: 근사 Delta(실험용 옵션, 기본 꺼짐)는 +947 = 거짓 상한('값 ≤ 947')을 반환",
          v_old == 947 and classify(v_old, MATE - 1, a, bb) == 'error', f"{v_old:+d}")
    s_ks = Searcher()
    s_ks.delta_pruning = True
    with ks_mode(True):
        v_ks = s_ks.quiesce(Board(cases[0][0]), a, bb, 0)
    check("재현 (King Safety 켬): 근사 Delta는 여전히 거짓 상한 (+962: 흑 킹 h8을 노리는 Qg1·Nh5 공격 -73이 phase 5/24로 더해짐)",
          v_ks == 962 and classify(v_ks, MATE - 1, a, bb) == 'error', f"{v_ks:+d}")

    errs_new = errs_old = bound_old = 0
    for fen, name, expect in cases:
        exact = ref_quiesce(Board(fen), -INF, INF, 0)
        if expect is not None and exact != expect:
            check(f"기준값 확인: {name}", False, f"{exact} != {expect}")
        new_kinds, old_kinds = [], []
        for wa, wb in windows_around(exact):
            r_new = Searcher().quiesce(Board(fen), wa, wb, 0)
            so = Searcher()
            so.delta_pruning = True
            r_old = so.quiesce(Board(fen), wa, wb, 0)
            new_kinds.append(classify(r_new, exact, wa, wb))
            old_kinds.append(classify(r_old, exact, wa, wb))
        errs_new += new_kinds.count('error')
        errs_old += old_kinds.count('error')
        bound_old += old_kinds.count('bound')
        check(f"{name}: 창 10가지 모두 정확값 또는 올바른 상·하한 (Delta 끔)",
              'error' not in new_kinds and new_kinds[0] == 'exact',
              f"정확값 {format_score(exact)}, 근사 Delta였다면 오류 {old_kinds.count('error')}개")

    # 무작위 국면: 기본 엔진은 오류 0. 근사 Delta는 '경계값 차이'와 '실제 오류'를 나눠 집계(참고용)
    fens = random_positions(60, 40, seed=17)
    in_check = [f for f in fens if Board(f).in_check()]
    pool = in_check[:40] + [f for f in fens if not Board(f).in_check()][::30]
    tested = new_err = old_err = old_bound = 0
    for f in pool:
        f0 = ' '.join(f.split()[:4]) + ' 0 1'
        if engine_quiesce(f0, node_limit=3000) is None:
            continue
        exact = ref_quiesce(Board(f0), -INF, INF, 0)
        tested += 1
        for wa, wb in windows_around(exact):
            new_err += classify(Searcher().quiesce(Board(f0), wa, wb, 0), exact, wa, wb) == 'error'
            so = Searcher()
            so.delta_pruning = True
            k = classify(so.quiesce(Board(f0), wa, wb, 0), exact, wa, wb)
            old_err += k == 'error'
            old_bound += k == 'bound'
    check(f"무작위 국면 {tested}개 × 창 10가지: Delta 끔은 오류 0 (정확값 또는 올바른 상·하한)",
          new_err == 0 and tested >= 60,
          f"참고: 근사 Delta였다면 실제 오류 {old_err}건, 단순 경계값 차이 {bound_old + old_bound}건")

    for fen, name, plies in (("7k/6pp/8/7N/8/8/8/6QK w - - 0 1", "1수 메이트", 1),
                             ("3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1", "2수 메이트", 3)):
        mv, sc, same = search_keeps_state(Board(fen), max_depth=1)
        check(f"search 깊이 1: {name}를 정적 탐색 안에서 찾음 ({format_score(MATE - plies)})",
              sc == MATE - plies and same, f"{mv.uci()} {format_score(sc)}")


def test_v032_draw_rules():
    section("v0.3.2-5.2  무승부: 청구 가능 vs 자동")
    s = Searcher()

    b = Board('8/8/8/4k3/8/8/8/R3K3 w - - 100 100')
    mv, sc, same = search_keeps_state(b, max_depth=3)
    check("① 50수 규칙: 청구 가능(claimable_draw)이지만 자동 종료 아님 → search는 수를 반환",
          b.claimable_draw() == '50수 규칙' and b.outcome() is None and mv is not None and same)

    x = "7k/6pp/8/7N/8/8/8/6QK w - - 100 1"
    mv, sc, same = search_keeps_state(Board(x), max_depth=3)
    check("② 청구 가능하지만 즉시 메이트: 루트에서 Qxg7# (#1)", mv.uci() == 'g1g7' and sc == MATE - 1 and same)
    s.root_len = 0
    n1 = s.negamax(Board(x), 2, -INF, INF, 1)
    q1 = Searcher().quiesce(Board(x), -INF, INF, 1)
    check("② 같은 국면이 내부 노드(ply 1)여도 0점이 아니라 메이트 점수 (v0.3.1: 0)",
          n1 == MATE - 2 and q1 == MATE - 2, f"negamax {n1}, quiesce {q1}")
    p = Board("6k1/6pp/8/7N/8/8/8/6QK b - - 99 1")       # 흑 차례, 흑의 킹 이동이 위 국면들을 만듦
    mv, sc, same = search_keeps_state(p, max_depth=4)
    check("② 상대의 청구 고려: 흑은 킹을 움직이며 50수 무승부 청구(FIDE 9.3.1) → 0점, 폰은 안 움직임",
          sc == 0 and mv.uci() in ('g8h8', 'g8f8', 'g8f7') and same, f"{mv.uci()} {format_score(sc)}")

    normal = Board('8/8/8/4k3/8/8/8/R3K3 b - - 0 100')    # 룩이 없는 흑 차례 (halfmove 0)
    lose = Board('8/8/8/4k3/8/8/8/R3K3 b - - 100 100')    # 같은 배치, 청구 가능
    sc0 = search_keeps_state(normal, max_depth=3)[1]
    mv, sc, same = search_keeps_state(lose, max_depth=3)
    inner = Searcher().negamax(Board(lose.fen()), 3, -INF, INF, 1)
    check("③ 불리한 쪽: 청구 불가면 지는 점수, 청구 가능하면 루트·내부 노드 모두 0점 (play.py가 청구)",
          sc0 < -300 and sc == 0 and inner == 0 and lose.claimable_draw() == '50수 규칙' and same,
          f"halfmove 0: {format_score(sc0)} / halfmove 100: 루트 {format_score(sc)}, 내부 {inner}")

    b = Board('8/8/8/4k3/8/8/8/R3K3 w - - 150 120')
    mv, sc, same = search_keeps_state(b, max_depth=3)
    check("④ 75수 규칙: 자동 무승부 → (None, 0)",
          b.outcome() == ('1/2-1/2', '75수 규칙') and (mv, sc) == (None, 0) and same)

    b = Board('7k/8/6K1/8/8/8/8/R7 w - - 149 80')
    mv, sc, same = search_keeps_state(b, max_depth=3)
    mated = Board('R6k/8/6K1/8/8/8/8/8 b - - 150 80')
    mv2, sc2, same2 = search_keeps_state(mated, max_depth=3)
    check("⑤ 75수째 수가 메이트면 메이트 우선: 탐색 Ra8# / 메이트된 국면은 75수가 아니라 체크메이트",
          mv.uci() == 'a1a8' and sc == MATE - 1 and mated.outcome() == ('1-0', '체크메이트')
          and (mv2, sc2) == (None, -MATE) and same and same2)

    cycle = "g1f3 g8f6 f3g1 f6g8".split()
    b = Board()
    for m in cycle * 2:
        b.push_uci(m)
    mv, sc, same = search_keeps_state(b, max_depth=3)
    check("⑥ 3회 동형반복: 청구 가능, 자동 종료 아님 → search는 수를 반환",
          b.claimable_draw() == '3회 동형반복' and b.outcome() is None and mv is not None and same)
    for m in cycle * 2:
        b.push_uci(m)
    mv, sc, same = search_keeps_state(b, max_depth=3)
    check("⑦ 5회 동형반복: 자동 무승부 → (None, 0)",
          b.outcome() == ('1/2-1/2', '5회 동형반복') and (mv, sc) == (None, 0) and same)

    # ⑧ 반복 이력이 다른 같은 국면: 한 Searcher로 번갈아 탐색해도 각각 빈 TT로 탐색한 값과 같아야 함
    hist = Board('4k3/8/8/8/8/8/8/R3K3 w - - 0 1')
    for m in "e1d1 e8d7 d1e1 d7e8 e1d1 e8d7 d1e1".split():
        hist.push_uci(m)                                # 흑 차례, Ke8이면 3번째 반복(청구 가능)
    plain_fen = hist.fen()
    shared = Searcher()
    results = []
    for which in ('plain', 'hist', 'plain', 'hist'):
        bd = hist if which == 'hist' else Board(plain_fen)
        warm = search_keeps_state(bd, max_depth=4, searcher=shared)[1]
        cold = search_keeps_state(hist if which == 'hist' else Board(plain_fen), max_depth=4)[1]
        results.append((which, warm, cold))
    ok = all(w == c for _, w, c in results) and results[1][1] == 0 and results[0][1] < -300
    check("⑧ 반복 이력만 다른 같은 국면을 한 TT로 번갈아 탐색: 매번 빈 TT 결과와 같음 (이력 있음 0점, 없음 지는 점수)",
          ok, ' / '.join(f"{w_}:{format_score(a_)}" for w_, a_, _ in results))

    # 탐색용 반복 근사와 실제 규칙의 구분
    s = Searcher()
    b = Board()
    for m in cycle:
        b.push_uci(m)
    s.root_len = len(b.history)                         # 시작 국면: 루트 이전 1번 + 지금 = 2번째
    k1 = s._repetition_kind(b)
    for m in cycle:
        b.push_uci(m)
    k2 = s._repetition_kind(b)                          # 루트 이후(트리 안)에서 다시 나옴
    s.root_len = len(b.history)
    k3 = s._repetition_kind(b)                          # 루트 이전에 2번 + 지금 = 3번째
    for m in cycle * 2:
        b.push_uci(m)
    s.root_len = len(b.history)
    k5 = s._repetition_kind(b)                          # 5번째
    check("반복 판정 구분: 2번째(기록) None / 트리 안 'tree'(탐색용 근사) / 3번째 'claim' / 5번째 'auto'",
          (k1, k2, k3, k5) == (None, 'tree', 'claim', 'auto'), f"{(k1, k2, k3, k5)}")


def test_v032_terminal_search():
    section("v0.3.2-5.3  이미 끝난 국면에서 search()")
    five = Board()
    for m in "g1f3 g8f6 f3g1 f6g8".split() * 4:
        five.push_uci(m)
    cases = [
        (Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"), "체크메이트", (None, -MATE)),
        (Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"), "스테일메이트", (None, 0)),
        (Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1"), "킹 대 킹", (None, 0)),
        (Board("4k3/8/8/8/2b5/8/8/4KB2 w - - 0 1"), "기물 부족(같은 색 비숍)", (None, 0)),
        (Board("8/8/8/4k3/8/8/8/R3K3 w - - 150 120"), "75수 규칙", (None, 0)),
        (five, "5회 동형반복", (None, 0)),
    ]
    for b, name, expect in cases:
        got = []
        same_all = True
        for kw in ({'max_depth': 4}, {'time_limit': 0.2}, {'node_limit': 50}):
            mv, sc, same = search_keeps_state(b, **kw)
            got.append((mv, sc))
            same_all &= same
        check(f"{name}: 수를 반환하지 않음 {expect} (깊이·시간·노드 한도 모두)",
              all(g == expect for g in got) and same_all and b.outcome() is not None)
    for fen, name in ((START_FEN, "시작 국면"), ("8/8/8/4k3/8/8/8/R3K3 w - - 100 100", "50수 청구 가능 국면")):
        b = Board(fen)
        mv, sc, same = search_keeps_state(b, max_depth=3)
        check(f"진행 중인 국면({name})은 이전처럼 합법수를 반환", mv in b.legal_moves() and same)


def test_v032_state_restore():
    section("v0.3.2-5.4  모든 탐색 전후 상태 유지 (fen · hash · len(history))")
    boards = []
    b = Board(TESTS[1][1])
    for m in ['e1g1', 'e8c8', 'd5e6', 'a6e2']:
        b.push_uci(m)
    boards.append(b)
    b = Board('4k3/8/8/8/8/8/8/R3K3 w - - 0 1')
    for m in "e1d1 e8d7 d1e1 d7e8 e1d1 e8d7 d1e1".split():
        b.push_uci(m)
    boards.append(b)
    boards += [Board("7k/6pp/8/7N/8/8/8/6QK w - - 100 1"), Board("6k1/6pp/8/7N/8/8/8/6QK b - - 99 1"),
               Board(TESTS[2][1]), Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")]
    ok = True
    runs = 0
    for b in boards:
        for kw in ({'max_depth': 4}, {'time_limit': 0.05}, {'node_limit': 1}, {'node_limit': 333},
                   {'node_limit': 4000}):
            ok &= search_keeps_state(b, **kw)[2]
            runs += 1
    check(f"국면 6개 × (깊이 4 / 시간 50ms / 노드 1·333·4000) = {runs}회 탐색 전후 상태 동일", ok)

    original = search_mod.evaluate
    ok = True
    for b in boards[:4]:
        calls = [0]

        def boom(bd):
            calls[0] += 1
            if calls[0] > 50:
                raise RuntimeError("강제 예외")
            return original(bd)

        fen0, h0, n0 = b.fen(), b.hash, len(b.history)
        search_mod.evaluate = boom
        try:
            Searcher().search(b, max_depth=6, on_info=None)
        except RuntimeError:
            pass
        finally:
            search_mod.evaluate = original
        ok &= (b.fen(), b.hash, len(b.history)) == (fen0, h0, n0)
    check("탐색 중 예외가 나도 국면 4개 모두 상태 동일", ok)


def test_v032_play_cli():
    section("v0.3.2  play.py 실제 실행 (입력을 자동으로 넣어 확인)")
    here = os.path.dirname(os.path.abspath(__file__))

    def play(stdin, *args):
        r = subprocess.run([sys.executable, os.path.join(here, 'play.py'), '--time', '0.2', *args],
                           input=stdin, capture_output=True, text=True, timeout=120, cwd=here)
        return r.returncode, r.stdout + r.stderr

    code, out = play("", "--fen", "4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    check("킹 대 킹으로 시작: 자동 종료 사유 출력, 오류 없음",
          code == 0 and "대국 종료 (자동): 1/2-1/2  — 기물 부족" in out and "Traceback" not in out)
    code, out = play("", "--fen", "8/8/8/4k3/8/8/8/R3K3 w - - 150 120", "--black")
    check("75수 규칙 국면, 엔진 차례로 시작: make_move(None) 없이 자동 종료",
          code == 0 and "75수 규칙" in out and "Traceback" not in out and "엔진의 수" not in out)
    code, out = play("a1a2\n", "--fen", "8/8/8/4k3/8/8/8/R3K3 w - - 99 100")
    check("50수 도달 후 지고 있는 엔진(흑)이 청구 → '청구'로 구분되어 종료",
          code == 0 and "대국 종료 (청구): 1/2-1/2  — 엔진의 청구: 50수 규칙" in out)
    code, out = play("draw\n", "--fen", "8/8/8/4k3/8/8/8/R3K3 w - - 100 100")
    check("사람이 청구 가능 안내를 받고 'draw'로 청구",
          "무승부 청구 가능: 50수 규칙" in out and "당신의 청구: 50수 규칙" in out)
    code, out = play("e2e4\ne7e5\ng1f3\nundo\nmoves\nquit\n")
    after_undo = out.rsplit("당신의 수>", 2)[-2]          # undo 다음 'moves' 출력
    check("일반 진행: 수 입력·엔진 응수 2번·잘못된 수 안내·무르기(Nf3 취소, e4 유지)·합법수 보기",
          code == 0 and out.count("엔진의 수:") == 2 and "둘 수 없는 수예요" in out
          and "g1f3" in after_undo and "e4e5" in after_undo and "e2e4" not in after_undo
          and "Traceback" not in out)
    code, out = play("a1a8\n", "--fen", "7k/8/6K1/8/8/8/8/R7 w - - 0 1")
    check("사람이 메이트: 체크메이트로 자동 종료", "대국 종료 (자동): 1-0  — 체크메이트" in out)
    code, out = play("", "--fen", "7k/6pp/8/7N/8/8/8/6QK w - - 100 1", "--black")
    check("청구 가능해도 엔진은 메이트(Qxg7#)를 둠",
          "엔진의 수: g1g7" in out and "1-0  — 체크메이트" in out and "청구" not in out.split("엔진의 수")[1])
    code, out = play("f1f7\n", "--fen", "7k/8/6K1/8/8/8/8/5Q2 w - - 0 1")
    check("사람의 수로 스테일메이트 → 자동 무승부", "대국 종료 (자동): 1/2-1/2  — 스테일메이트" in out)
    # 흑 킹이 h8↔g8만 오갈 수 있는 국면: 사람이 킹을 왕복하면 같은 국면이 반복됨
    code, out = play("c3c4\nc4c3\nc3c4\nc4c3\nquit\n", "--fen", "7k/R7/8/8/8/2K5/5R2/8 w - - 0 1")
    check("지고 있는 엔진이 '이 수를 두며' 3회 반복 청구 (FIDE 9.2.1.1)",
          "대국 종료 (청구): 1/2-1/2  — 엔진이 g8h8를 두며 청구: 3회 동형반복" in out)
    code, out = play("draw e5d5\n", "--fen", "8/8/8/4k3/8/8/8/R3K3 b - - 99 100", "--black")
    check("사람이 'draw e5d5'로 수를 두며 50수 규칙 청구 (FIDE 9.3.1)",
          "당신이 e5d5를 두며 청구: 50수 규칙" in out)
    code, out = play("", "--fen", "7k/6Q1/8/6K1/8/8/8/8 w - - 0 1")
    check("불가능한 국면의 FEN: Traceback 없이 오류 메시지와 종료 코드 2",
          code == 2 and "시작할 수 없어요" in out and "Traceback" not in out)


# ═══════════════════════════════ v0.3.3 추가 테스트: 언더프로모션 ═══════════════════════════════
try:                                     # 선택: 독립 라이브러리 교차 검증 (엔진 의존성 아님)
    import chess as pychess
except ImportError:
    pychess = None

SKIPPED = []


def skip(name, reason):
    SKIPPED.append((GROUP[0], name))
    print(f"  [건너뜀] {name}  ({reason})")


def pc_quiesce(pb, alpha, beta, ply):
    """python-chess로 수 생성·체크·메이트·스테일메이트를 판정하는 세 번째 기준 구현.
    평가값만 우리 evaluate()를 씀 (정적 탐색 정의 비교가 목적이므로)."""
    legal = list(pb.legal_moves)
    if not legal:
        return -MATE + ply if pb.is_check() else 0
    if pb.is_check():
        best, cand = -INF, legal
    else:
        best = evaluate(Board(pb.fen()))
        if best >= beta:
            return best
        alpha = max(alpha, best)
        cand = [m for m in legal if pb.is_capture(m) or m.promotion]
    cand.sort(key=lambda m: ((pb.piece_type_at(m.to_square) or 0), m.promotion or 0), reverse=True)
    for m in cand:
        pb.push(m)
        score = -pc_quiesce(pb, -beta, -alpha, ply + 1)
        pb.pop()
        if score > best:
            best = score
            alpha = max(alpha, score)
            if alpha >= beta:
                break
    return best


def promo_positions(n, seed):
    """승격이 많이 나오는 무작위 합법 국면: 7랭크 백 폰 1~3개, 2랭크 흑 폰 0~3개, 기물 0~4개"""
    rng = random.Random(seed)
    out = []
    while len(out) < n:
        cells = ['.'] * 64
        free = list(range(64))
        rng.shuffle(free)

        def put(p, allowed):
            for i, c in enumerate(free):
                if c in allowed:
                    cells[c] = p
                    free.pop(i)
                    return

        put('K', range(64))
        put('k', range(64))
        for _ in range(rng.randint(1, 3)):
            put('P', range(48, 56))
        for _ in range(rng.randint(0, 3)):
            put('p', range(8, 16))
        for _ in range(rng.randint(0, 4)):
            put(rng.choice('NBRQnbrq'), range(64))
        rows = []
        for r in range(7, -1, -1):
            row, e = '', 0
            for f in range(8):
                p = cells[r * 8 + f]
                if p == '.':
                    e += 1
                else:
                    row += (str(e) if e else '') + p
                    e = 0
            rows.append(row + (str(e) if e else ''))
        try:
            b = Board('/'.join(rows) + rng.choice((' w', ' b')) + ' - - 0 1')
        except ValueError:
            continue
        if b.outcome() is None and any(m.promo for m in b.legal_moves()):
            out.append(b.fen())
    return out


def root_moves_searched(fen):
    """정적 탐색(전체 창)이 루트에서 실제로 두어 본 수 목록 (make_move를 가로채서 기록)"""
    b = Board(fen)
    base = len(b.history)
    seen = []
    orig = b.make_move

    def spy(m):
        if len(b.history) == base:
            seen.append(m.uci())
        orig(m)

    b.make_move = spy
    v = Searcher().quiesce(b, -INF, INF, 0)
    return v, seen


def state_of(b):
    return b.fen(), b.hash, len(b.history)


POS_A = "6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1"          # 나이트 승격만 메이트, 나머지 3종은 스테일메이트
POS_B = "8/4P3/8/8/8/8/k7/4K3 w - - 0 1"             # 평범한 퀸 승격 (다음 수에 해도 이김)
POS_B1 = "k7/4P2r/8/8/8/8/8/K7 w - - 0 1"            # 흑 룩이 e7을 노림 → 지금 퀸 승격해야 함
POS_B2 = "r3k3/1P6/8/8/8/8/8/4K3 w - - 0 1"          # 잡으며 퀸 승격 (bxa8=Q+)
POS_C = "5r2/4P1K1/4k3/2Q5/8/8/8/8 w - - 0 1"        # 잡으며 승격 e7xf8 4종, 나이트만 메이트
POS_D = "8/5P1k/5K2/8/8/8/8/8 w - - 0 1"             # 퀸 승격은 스테일메이트, 룩 승격 = 2수 메이트
POS_E = "8/8/8/8/8/5kr1/5p1K/6r1 b - - 0 1"          # A의 흑 버전 (f2f1n#)
POS_E2 = "8/8/8/8/2q5/4K3/4p1k1/5R2 b - - 0 1"       # C의 흑 버전 (e2xf1=N#)
POS_E3 = "8/8/8/8/8/5k2/5p1K/8 b - - 0 1"            # D의 흑 버전 (f2f1r!)


def test_v033_A_knight_mate():
    section("v0.3.3-A  나이트 승격 체크메이트 (6R1/5P1k/5KR1/8/8/8/8/8 w)")
    b = Board(POS_A)
    promos = sorted(m.uci() for m in b.legal_moves() if m.promo)
    check("1. 합법수에 승격 4종이 있음", promos == ['f7f8b', 'f7f8n', 'f7f8q', 'f7f8r'], ' '.join(promos))
    expect = {'f7f8q': '스테일메이트', 'f7f8r': '스테일메이트', 'f7f8b': '스테일메이트', 'f7f8n': '체크메이트'}
    got = {}
    for u in expect:
        b.push_uci(u)
        got[u] = (b.outcome() or (None, None))[1]
        b.unmake_move()
    check("2. 승격 후 outcome: Q·R·B는 스테일메이트, N은 체크메이트", got == expect, str(got))
    v = Searcher().quiesce(Board(POS_A), -INF, INF, 0)
    check("3·4. 정적 탐색이 나이트 승격 메이트를 찾고, 전체 창 값 = MATE - 1 (v0.3.2: +12.77)",
          v == MATE - 1, f"{v}")
    picks = [quiet_search(Board(POS_A), max_depth=d) for d in (1, 2, 3)]
    check("5. 일반 탐색(깊이 1~3)도 f7f8n, #1", all(m.uci() == 'f7f8n' and s == MATE - 1 for m, s in picks))
    r = ref_quiesce(Board(POS_A), -INF, INF, 0)
    check("6. 독립 기준 구현(ref_quiesce)과 값이 같음", r == v, f"ref {r}")
    if pychess:
        pb = pychess.Board(POS_A)
        pc_out = {}
        for u in expect:
            pb.push_uci(u)
            pc_out[u] = '체크메이트' if pb.is_checkmate() else '스테일메이트' if pb.is_stalemate() else None
            pb.pop()
        check("6. python-chess: 승격 결과와 정적 탐색 값이 모두 같음",
              pc_out == expect and pc_quiesce(pychess.Board(POS_A), -INF, INF, 0) == v)
    else:
        skip("6. python-chess 교차 검증", "python-chess 미설치")


def test_v033_B_queen_promo():
    section("v0.3.3-B  평범한 퀸 승격이 손상되지 않음")

    def promo_values():
        v = Searcher().quiesce(Board(POS_B), -INF, INF, 0)
        b = Board(POS_B)
        child = {}
        for m in b.legal_moves():
            if m.promo:
                b.make_move(m)
                child[m.promo] = -Searcher().quiesce(b, -INF, INF, 1, check_rules=False)
                b.unmake_move()
        return v, child, ref_quiesce(Board(POS_B), -INF, INF, 0)
    with king_safety_off():                   # +9.00은 v0.4.0까지의 평가로 나온 값
        v, child, ref = promo_values()
    check("e7e8: 정적 탐색 값 +9.00 (v0.3.2와 같음), 승격 4종 중 퀸 승격이 가장 높음",
          v == 900 and v == ref and max(child, key=child.get) == 'q',
          f"{format_score(v)}, " + ' '.join(f"{k}:{format_score(s)}" for k, s in child.items()))
    with ks_mode(True):
        v, child, ref = promo_values()
    check("e7e8 (King Safety 켬): 값 = 독립 기준 구현, 퀸 승격이 가장 높음 "
          "(v0.4.2 공식: +9.00 — 퀸 하나만으로는 공격력 부족이라 벌점 없음. v0.4.1 공식에서는 +9.05였음)",
          v == 900 and v == ref and max(child, key=child.get) == 'q',
          f"{format_score(v)}, " + ' '.join(f"{k}:{format_score(s)}" for k, s in child.items()))
    picks = [quiet_search(Board(POS_B1), max_depth=d)[0].uci() for d in (2, 3, 4, 5)]
    check("룩이 폰을 노리는 국면: 깊이 2~5 모두 지금 퀸 승격(e7e8q)을 고름 (v0.3.2와 같음)",
          picks == ['e7e8q'] * 4, ' '.join(picks))
    v2 = Searcher().quiesce(Board(POS_B2), -INF, INF, 0)
    mv2, sc2 = quiet_search(Board(POS_B2), max_depth=4)
    caps = sorted(m.uci() for m in Board(POS_B2).legal_moves() if m.promo and m.to == parse_sq('a8'))
    check("bxa8=Q+: 잡으며 승격 4종이 생성되고, 엔진은 퀸 승격을 고름",
          caps == ['b7a8b', 'b7a8n', 'b7a8q', 'b7a8r'] and mv2.uci() == 'b7a8q'
          and v2 == ref_quiesce(Board(POS_B2), -INF, INF, 0), f"{mv2.uci()} {format_score(sc2)}")


def test_v033_C_capture_underpromo():
    section("v0.3.3-C  잡으며 하는 언더프로모션 (e7xf8)")
    b = Board(POS_C)
    caps = sorted(m.uci() for m in b.legal_moves() if m.promo and m.to == parse_sq('f8'))
    check("e7f8q/r/b/n 4종 모두 합법수로 생성", caps == ['e7f8b', 'e7f8n', 'e7f8q', 'e7f8r'])
    qs_gen = [m.uci() for m in b.pseudo_legal_moves(captures_only=True) if m.promo]
    check("정적 탐색용 생성(captures_only)에 승격 8종(전진 4 + 잡기 4)이 중복 없이 있음",
          len(qs_gen) == 8 and len(set(qs_gen)) == 8, ' '.join(sorted(qs_gen)))
    v, seen = root_moves_searched(POS_C)
    check("정적 탐색이 루트에서 잡기 승격 4종을 모두 실제로 두어 봄 (전체 창 = 루트 가지치기 없음)",
          {'e7f8q', 'e7f8r', 'e7f8b', 'e7f8n'} <= set(seen), ' '.join(seen))
    mv, sc = quiet_search(Board(POS_C), max_depth=3)
    check("e7xf8=N# 이 유일한 메이트: 정적 탐색 MATE-1, 일반 탐색 e7f8n, 기준 구현과 일치",
          v == MATE - 1 and mv.uci() == 'e7f8n' and sc == MATE - 1
          and ref_quiesce(Board(POS_C), -INF, INF, 0) == v)


def test_v033_D_stalemate_avoid():
    section("v0.3.3-D  퀸 승격은 스테일메이트 → 룩 승격으로 승리")
    b = Board(POS_D)
    b.push_uci('f7f8q')
    q_out = b.outcome()
    b.unmake_move()
    b.push_uci('f7f8r')
    r_out = b.outcome()
    b.unmake_move()
    check("f7f8q는 스테일메이트, f7f8r은 대국 계속 (승리 국면이라 스테일메이트는 손해)",
          q_out == ('1/2-1/2', '스테일메이트') and r_out is None)
    v = Searcher().quiesce(Board(POS_D), -INF, INF, 0)
    check("정적 탐색: 퀸 승격(0점) 대신 룩 승격으로 +5점대, 기준 구현과 일치",
          v > 300 and v == ref_quiesce(Board(POS_D), -INF, INF, 0), format_score(v))
    picks = [quiet_search(Board(POS_D), max_depth=d) for d in (1, 2, 3, 4, 5)]
    check("깊이 1~5 어디서도 f7f8q를 두지 않음", all(m.uci() != 'f7f8q' for m, _ in picks),
          ' '.join(m.uci() for m, _ in picks))
    m4, s4 = picks[3]
    child = Board(POS_D)
    child.push_uci(m4.uci())
    check("깊이 4 이상: 유일한 2수 메이트 f7f8r! (#2, 완전 탐색으로 확인)",
          m4.uci() == 'f7f8r' and s4 == MATE - 3 and gets_mated_within(child, 1)
          and min_mate(Board(POS_D), 2) == 2, f"{m4.uci()} {format_score(s4)}")


def test_v033_E_black():
    section("v0.3.3-E  흑의 언더프로모션 (1랭크 승격)")
    for fen, mate_mv, name in ((POS_E, 'f2f1n', "흑 전진 승격 f2f1=N#"),
                               (POS_E2, 'e2f1n', "흑 잡으며 승격 e2xf1=N#")):
        b = Board(fen)
        results = {}
        for m in b.legal_moves():
            if m.promo:
                b.make_move(m)
                results[m.uci()] = (b.outcome() or (None, '-'))[1]
                b.unmake_move()
        v = Searcher().quiesce(Board(fen), -INF, INF, 0)
        mv, sc = quiet_search(Board(fen), max_depth=3)
        only_mate = [u for u, r in results.items() if r == '체크메이트'] == [mate_mv]
        check(f"{name}: 4종 생성, 나이트만 메이트, 정적 탐색 MATE-1, 일반 탐색 {mate_mv}",
              only_mate and v == MATE - 1 and mv.uci() == mate_mv and sc == MATE - 1, str(results))
    for white_fen, black_fen in ((POS_A, POS_E), (POS_C, POS_E2), (POS_D, POS_E3)):
        w = Searcher().quiesce(Board(white_fen), -INF, INF, 0)
        k = Searcher().quiesce(Board(black_fen), -INF, INF, 0)
        if w != k or mirror(Board(white_fen)).fen().split()[0] != Board(black_fen).fen().split()[0]:
            check("백·흑 대칭", False, f"{white_fen}: {w} / {black_fen}: {k}")
    check("백 국면 A·C·D와 색만 뒤집은 흑 국면의 정적 탐색 값이 같음", True)
    mv, sc = quiet_search(Board(POS_E3), max_depth=4)
    check("흑도 퀸 승격 스테일메이트를 피하고 f2f1r! (#2)", mv.uci() == 'f2f1r' and sc == MATE - 3,
          f"{mv.uci()} {format_score(sc)}")


def test_v033_F_windows():
    section("v0.3.3-F  승격 국면의 Alpha-Beta 경계 (정확값 / 하한 / 상한 구분)")
    counts = {'exact': 0, 'lower': 0, 'upper': 0}
    errors = []
    for fen in (POS_A, POS_B, POS_B2, POS_C, POS_D, POS_E, POS_E2, POS_E3):
        exact = ref_quiesce(Board(fen), -INF, INF, 0)
        wins = [(-INF, INF, '전체 창'), (exact - 1, exact + 1, '정확값을 포함하는 좁은 창'),
                (exact - 50, exact + 50, '정확값 포함'), (exact - 300, exact - 100, 'fail-high (창이 정답 아래)'),
                (exact + 100, exact + 300, 'fail-low (창이 정답 위)'), (-INF, exact - 1, 'fail-high'),
                (exact + 1, INF, 'fail-low'), (exact, exact + 1, '경계 = 정답 (alpha)'),
                (exact - 1, exact, '경계 = 정답 (beta)')]
        for a, bb, label in wins:
            before = state_of(Board(fen))
            bd = Board(fen)
            r = Searcher().quiesce(bd, a, bb, 0)
            kind = classify(r, exact, a, bb)
            if kind == 'error' or state_of(bd) != before:
                errors.append(f"{fen} {label}: {r} (정답 {exact})")
            elif a < exact < bb:
                counts['exact'] += 1
            elif exact >= bb:
                counts['lower'] += 1
            else:
                counts['upper'] += 1
    check("승격 국면 8개 × 창 9가지: 창 안이면 정확값, fail-high면 올바른 하한, fail-low면 올바른 상한",
          not errors, f"정확 {counts['exact']} / 하한 {counts['lower']} / 상한 {counts['upper']}"
          + (f" / 오류: {errors[:2]}" if errors else ''))


def test_v033_G_state():
    section("v0.3.3-G  승격 탐색 전후 상태 복구")
    fens = [POS_A, POS_B, POS_B2, POS_C, POS_D, POS_E, POS_E2, POS_E3] + promo_positions(40, seed=3)
    ok_q = ok_mm = ok_s = True
    promo_count = 0
    for fen in fens:
        board = Board(fen)
        original = state_of(board)
        Searcher().quiesce(board, -INF, INF, 0)
        ok_q &= state_of(board) == original
        for m in board.legal_moves():
            if m.promo:
                promo_count += 1
                board.make_move(m)
                ok_mm &= board.hash == board.compute_hash()
                board.unmake_move()
                ok_mm &= state_of(board) == original
        for kw in ({'max_depth': 3}, {'node_limit': 200}, {'time_limit': 0.02}):
            ok_s &= search_keeps_state(board, **kw)[2]
    check(f"국면 {len(fens)}개: quiesce 전후 fen·hash·history 길이 동일", ok_q)
    check(f"승격 수 {promo_count}개: make 후 해시 = 처음부터 계산한 값, unmake 후 원래 상태", ok_mm)
    check("search(깊이 3 / 노드 200 / 시간 20ms) 전후 상태 동일", ok_s)


def test_v033_extra():
    section("v0.3.3  추가 검토 ①~⑤")
    fens = promo_positions(300, seed=11)

    # ① 중복 생성
    dup = mismatch = bad_variants = 0
    for f in fens:
        b = Board(f)
        full = b.pseudo_legal_moves()
        caps = b.pseudo_legal_moves(captures_only=True)
        dup += len(full) != len(set(full)) or len(caps) != len(set(caps))
        mismatch += {m for m in full if m.promo} != {m for m in caps if m.promo}
        squares = {}
        for m in full:
            if m.promo:
                squares.setdefault((m.frm, m.to), []).append(m.promo)
        bad_variants += any(sorted(v) != ['b', 'n', 'q', 'r'] for v in squares.values())
    check(f"① 승격 국면 {len(fens)}개: 중복 수 없음, 정적 탐색용 승격 = 전체 승격, 칸마다 정확히 4종",
          dup == mismatch == bad_variants == 0, f"중복 {dup}, 불일치 {mismatch}, 종류 오류 {bad_variants}")

    # ② 메이트·스테일메이트 구분
    wrong = n_mate = n_stale = 0
    for f in fens:
        b = Board(f)
        for m in b.legal_moves():
            if not m.promo:
                continue
            b.make_move(m)
            oc = b.outcome()
            v = Searcher().quiesce(b, -INF, INF, 1, check_rules=False)
            if oc and oc[1] == '체크메이트':
                n_mate += 1
                wrong += v != -MATE + 1
            elif oc and oc[1] == '스테일메이트':
                n_stale += 1
                wrong += v != 0
            if pychess:
                pb = pychess.Board(b.fen())
                ours = oc[1] if oc and oc[1] in ('체크메이트', '스테일메이트') else None
                theirs = '체크메이트' if pb.is_checkmate() else '스테일메이트' if pb.is_stalemate() else None
                wrong += ours != theirs
            b.unmake_move()
    check(f"② 모든 승격 직후: 메이트 {n_mate}개는 -MATE+1, 스테일메이트 {n_stale}개는 0"
          + (" (python-chess 판정과도 일치)" if pychess else ""), wrong == 0 and n_mate > 0 and n_stale > 0,
          f"불일치 {wrong}")

    # ③ 종료 조건: 승격·체크가 섞인 국면에서도 정적 탐색이 끝남
    max_nodes = 0
    unfinished = 0
    for f in fens:
        s = Searcher()
        s.node_limit = 500_000
        try:
            s.quiesce(Board(f), -INF, INF, 0)
        except search_mod.TimeUp:
            unfinished += 1
        max_nodes = max(max_nodes, s.nodes)
    check(f"③ 승격 국면 {len(fens)}개 모두 정적 탐색 종료 (노드 50만 한도)", unfinished == 0,
          f"최대 {max_nodes:,} 노드")

    # ④ 중단 후 상태 복구
    ok = True
    for f in fens[:60]:
        b = Board(f)
        before = state_of(b)
        for lim in (1, 7, 64, 500):
            mv, _ = Searcher().search(b, node_limit=lim, on_info=None)
            ok &= state_of(b) == before and mv in b.legal_moves()
    check("④ 승격 국면 60개 × 노드 한도 4가지로 끊어도 상태 복구 + 합법수 반환", ok)

    # ⑤ 독립 기준 구현과 비교
    cmp = 0
    diffs = []
    pc_diffs = []
    for f in fens:
        if engine_quiesce(f, node_limit=3000) is None:
            continue
        cmp += 1
        e = Searcher().quiesce(Board(f), -INF, INF, 0)
        r = ref_quiesce(Board(f), -INF, INF, 0)
        if e != r:
            diffs.append((f, e, r))
        if pychess:
            p = pc_quiesce(pychess.Board(f), -INF, INF, 0)
            if p != e:
                pc_diffs.append((f, e, p))
    check(f"⑤ 승격 국면 {cmp}개: 엔진 정적 탐색 = ref_quiesce (기물 구성 변화로 후보를 고르는 독립 구현)",
          not diffs and cmp >= 150, f"불일치 {len(diffs)} {diffs[:1]}")
    if pychess:
        check(f"⑤ 같은 {cmp}개: 엔진 = python-chess 기반 기준 구현 (수 생성·메이트 판정까지 독립)",
              not pc_diffs, f"불일치 {len(pc_diffs)} {pc_diffs[:1]}")
        legal_bad = 0
        for f in fens + random_positions(20, 40, seed=5):
            ours = sorted(m.uci() for m in Board(f).legal_moves())
            theirs = sorted(m.uci() for m in pychess.Board(f).legal_moves)
            legal_bad += ours != theirs
        check("⑤ 합법수 목록(승격 포함)이 python-chess와 완전히 같음 (승격 국면 300 + 일반 국면 800)",
              legal_bad == 0, f"불일치 {legal_bad}")
    else:
        skip("⑤ python-chess 교차 검증", "python-chess 미설치 — pip install chess 후 다시 실행")


HORIZON_FENS = [                         # 흑이 백 기물(미끼)을 잡으면 백의 나이트 승격 메이트가 생기는 국면
    "6R1/5P1k/5KR1/8/2Q5/8/2q5/8 b - - 0 1",
    "6R1/5P1k/5KR1/8/8/8/3n4/5Q2 b - - 0 1",
    "6R1/5P1k/5KR1/8/8/8/q7/1Q6 b - - 0 1",
    "6R1/5P1k/5KR1/1r6/8/8/1Q6/8 b - - 0 1",
    "6R1/5P1k/5KR1/4n3/2Q5/8/8/8 b - - 0 1",
    "6R1/5P1k/5KR1/8/2Q5/8/3n4/8 b - - 0 1",
]


def allows_mate_in_one(b, m):
    """흑의 수 m 뒤에 백이 1수 메이트를 할 수 있는가 (outcome으로 판정)"""
    b.make_move(m)
    try:
        for w in b.legal_moves():
            b.make_move(w)
            mate = (b.outcome() or (None, ''))[1] == '체크메이트'
            b.unmake_move()
            if mate:
                return True
        return False
    finally:
        b.unmake_move()


def test_v033_horizon():
    section("v0.3.3  탐색 깊이 끝(정적 탐색)의 언더프로모션")
    ok = 0
    detail = []
    for fen in HORIZON_FENS:
        b = Board(fen)
        mv, sc, same = search_keeps_state(b, max_depth=1)
        safe = not allows_mate_in_one(b, mv)
        ok += safe and same
        detail.append(mv.uci())
    check(f"깊이 1: 미끼를 잡지 않고 상대의 나이트 승격 메이트를 막음 {ok}/{len(HORIZON_FENS)} (v0.3.2: 0/6)",
          ok == len(HORIZON_FENS), ' '.join(detail))


def test_v033_play_cli():
    section("v0.3.3  play.py 승격 입력")
    here = os.path.dirname(os.path.abspath(__file__))

    def play(stdin, *args):
        r = subprocess.run([sys.executable, os.path.join(here, 'play.py'), '--time', '0.2', *args],
                           input=stdin, capture_output=True, text=True, timeout=120, cwd=here)
        return r.returncode, r.stdout + r.stderr

    code, out = play("f7f8\nF7F8N\n", "--fen", POS_A)
    check("사람: 승격 문자 없는 'f7f8'은 거부, 대문자 'F7F8N'은 나이트 승격 → 체크메이트",
          "둘 수 없는 수예요" in out and "대국 종료 (자동): 1-0  — 체크메이트" in out and "Traceback" not in out)
    code, out = play("", "--fen", POS_E)
    check("엔진(흑): f2f1n으로 메이트", "엔진의 수: f2f1n" in out and "0-1  — 체크메이트" in out)


# ═══════════════════════════════ v0.4.1 추가 테스트 ═══════════════════════════════
def test_v041_root_moves():
    section("v0.4.1-1  루트 후보 제한 (UCI go searchmoves)")
    rng = random.Random(1)
    fens = random_positions(6, 30, seed=2)[::25][:12]
    exact = total = 0
    for f in fens:
        b = Board(f)
        legal = b.legal_moves()
        if len(legal) < 4:
            continue
        cands = rng.sample(legal, 3)
        before = state_of(b)
        mv, sc = Searcher().search(b, max_depth=3, on_info=None, root_moves=cands)
        each = {c.uci(): Searcher().search(b, max_depth=3, on_info=None, root_moves=[c])[1] for c in cands}
        total += 1
        exact += mv in cands and sc == max(each.values()) and each[mv.uci()] == sc and state_of(b) == before
    check(f"후보 3개로 제한: 고른 수 = 후보를 하나씩 따로 탐색한 점수가 가장 높은 수 ({exact}/{total}국면)",
          exact == total and total >= 6)

    b = Board()
    mv, sc = Searcher().search(b, max_depth=3, on_info=None, root_moves=['a2a3', 'h2h4', 'zz9', 'e2e5', 'E7E5'])
    check("불법수·잘못된 표기는 무시하고 합법 후보(a2a3, h2h4) 중에서만 고름", mv.uci() in ('a2a3', 'h2h4'), mv.uci())
    check("합법 후보가 하나도 없으면 (None, 0)",
          Searcher().search(Board(), max_depth=3, on_info=None, root_moves=['e2e5', 'e7e5']) == (None, 0)
          and Searcher().search(Board(), max_depth=3, on_info=None, root_moves=[]) == (None, 0))
    check("이미 끝난 국면은 후보와 무관하게 (None, -MATE)",
          Searcher().search(Board("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"), max_depth=2, on_info=None,
                            root_moves=['h8h7']) == (None, -MATE))

    m1 = Board("7k/8/6K1/8/8/8/8/R7 w - - 0 1")               # Ra8# 이 있는 국면
    mv, sc = Searcher().search(m1, max_depth=4, on_info=None, root_moves=['a1a2', 'a1b1'])
    mv2, sc2 = Searcher().search(m1, max_depth=4, on_info=None, root_moves=['a1a2', 'a1a8'])
    check("1수 메이트(Ra8#)를 후보에서 빼면 #1이 아님(더 늦은 메이트) / 넣으면 #1",
          mv.uci() in ('a1a2', 'a1b1') and sc < MATE - 1 and mv2.uci() == 'a1a8' and sc2 == MATE - 1,
          f"{mv.uci()} {format_score(sc)} / {mv2.uci()} {format_score(sc2)}")

    s = Searcher()
    pos = Board(TESTS[5][1])
    s.search(pos, max_depth=4, on_info=None, root_moves=[pos.legal_moves()[-1]])
    warm = s.search(pos, max_depth=4, on_info=None)
    cold = Searcher().search(pos, max_depth=4, on_info=None)
    check("제한 탐색의 루트 점수는 TT에 남기지 않음: 뒤이은 일반 탐색 = 빈 TT로 한 탐색",
          warm == cold, f"{warm[0].uci()} {warm[1]} / {cold[0].uci()} {cold[1]}")
    mv, sc = Searcher().search(Board(), max_depth=99, node_limit=50, on_info=None, root_moves=['g2g4', 'b1a3'])
    check("깊이 1도 못 끝내고 멈춰도 후보 안의 합법수를 냄", mv.uci() in ('g2g4', 'b1a3'), mv.uci())


def test_v041_node_limit():
    section("v0.4.1-2  노드 한도를 정확히 지킴 (UCI go nodes)")
    ok = True
    detail = []
    for fen in (START_FEN, TESTS[1][1], TESTS[2][1], POS_D):
        free = Searcher()
        free.search(Board(fen), max_depth=6, on_info=None)       # 한도 없이 깊이 6까지의 탐색량
        for lim in (1, 2, 333, 1023, 1024, 1025, 4097, 20000):
            b = Board(fen)
            before = state_of(b)
            s = Searcher()
            mv, _ = s.search(b, max_depth=6, node_limit=lim, on_info=None)
            good = s.nodes == min(lim, free.nodes) and mv in b.legal_moves() and state_of(b) == before
            ok &= good
            if not good:
                detail.append(f"{lim}->{s.nodes}")
    check("국면 4개 × 한도 8가지: 노드 수 = min(한도, 한도 없을 때 탐색량) (v0.4.0은 최대 1023 초과), 합법수, 상태 복구",
          ok, ' '.join(detail))
    s = Searcher()
    s.search(Board(), max_depth=3, on_info=None)
    small = s.nodes
    s2 = Searcher()
    s2.search(Board(), max_depth=3, node_limit=10 ** 6, on_info=None)
    check("한도보다 일찍 끝나는 탐색은 한도와 무관하게 같은 결과", s2.nodes == small)


KIWI = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"


def watch_tt(s):
    """s.tt.store를 감싸 탐색 '도중'의 최대 항목 수를 기록. [최대값] 리스트를 돌려줌."""
    peak = [0]
    orig = s.tt.store

    def store(*a):
        orig(*a)
        if len(s.tt) > peak[0]:
            peak[0] = len(s.tt)
    s.tt.store = store
    return peak


def filled_slots(tt):
    return sum(e is not None for e in tt.slots)


def test_v041_tt_capacity():
    section("v0.4.1-3  TT 용량 제한 (탐색 중에도 용량을 넘지 않음)")
    # 요청서의 검증 코드 그대로 (+ 탐색 도중 최대값도 확인)
    board = Board()
    searcher = Searcher(tt_size=1000)
    peak = watch_tt(searcher)
    before = state_of(board)
    mv, _ = searcher.search(board, max_depth=6, on_info=None)
    check("Searcher(tt_size=1000), 시작 국면 깊이 6: len(tt) <= 1000, 탐색 도중 최대도 <= 1000 "
          "(v0.4.0 dict는 탐색 도중 제한 없음)",
          len(searcher.tt) <= 1000 and peak[0] <= 1000 and mv in board.legal_moves() and state_of(board) == before,
          f"끝 {len(searcher.tt)}, 도중 최대 {peak[0]}, 노드 {searcher.nodes:,}")
    check("저장된 항목 수(len)와 실제로 찬 칸 수가 같음", len(searcher.tt) == filled_slots(searcher.tt),
          f"{len(searcher.tt)} / {filled_slots(searcher.tt)}")

    ok, detail = True, []
    for cap in (0, 1, 2, 3, 17, 1000):
        for fen in (KIWI, TESTS[2][1], POS_D):
            b = Board(fen)
            s = Searcher(tt_size=cap)
            peak = watch_tt(s)
            mv, _ = s.search(b, max_depth=4, on_info=None)
            good = (len(s.tt) <= cap and peak[0] <= cap and len(s.tt) == filled_slots(s.tt)
                    and mv in b.legal_moves())
            ok &= good
            if not good:
                detail.append(f"{cap}:{len(s.tt)}/{peak[0]}")
    check("용량 0·1·2·3·17·1000 × 국면 3개: 항목 수 <= 용량(도중 포함), 합법수 (0·1이면 TT 없이 탐색)",
          ok, ' '.join(detail))

    s = Searcher(tt_size=1000)
    s.search(Board(KIWI), max_depth=3, on_info=None)
    for _ in range(3):                                   # 여러 번 탐색해도 쌓이지 않음
        s.search(Board(KIWI), max_depth=4, on_info=None)
    n_full = len(s.tt)
    s.tt_size = 500
    check("여러 번 탐색해도 용량 유지 / tt_size를 바꾸면 그 용량의 빈 표로 바뀜",
          n_full <= 1000 and s.tt_size == 500 and len(s.tt) == 0 and len(s.tt.slots) == 500,
          f"{n_full} → 용량 {s.tt_size}, 항목 {len(s.tt)}")
    s.search(Board(KIWI), max_depth=4, on_info=None)
    filled = len(s.tt)
    s.tt.clear()
    check("clear(): 항목 0, 용량은 그대로, 조회 결과 없음",
          filled > 0 and len(s.tt) == 0 and s.tt_size == 500 and s.tt.get(Board(KIWI).hash) is None,
          f"{filled} → {len(s.tt)}")


def test_v041_tt_replacement():
    section("v0.4.1-4  TT 교체 정책 (깊이 우선 + 항상 교체 + 세대)")
    t = TranspositionTable(8)                    # 버킷 4개 × 2칸
    nb = t.nbuckets
    A, B, C, D, E = 5, 5 + nb, 5 + 2 * nb, 5 + 3 * nb, 5 + 4 * nb   # 모두 같은 버킷
    t.new_search()
    t.store(A, 8, EXACT, 11, None)
    t.store(B, 2, LOWER, 22, None)
    check("같은 버킷의 두 국면은 둘 다 저장 (깊은 A는 첫째 칸, 얕은 B는 둘째 칸)",
          t.get(A)[:3] == (8, EXACT, 11) and t.get(B)[:3] == (2, LOWER, 22) and len(t) == 2)
    t.store(C, 3, UPPER, 33, None)
    check("같은 세대: 더 얕은 새 결과 C는 둘째 칸(B)만 교체, 깊은 A는 보존",
          t.get(A) is not None and t.get(B) is None and t.get(C)[2] == 33 and len(t) == 2)
    t.store(D, 9, EXACT, 44, None)
    check("더 깊은 새 결과 D는 첫째 칸 차지, 밀려난 A는 둘째 칸으로 (C는 버림)",
          t.slots[2 * (A % nb)][4] == D and t.get(A)[2] == 11 and t.get(C) is None and len(t) == 2)
    t.store(A, 1, LOWER, 55, None)
    check("이미 있는 국면은 깊이와 무관하게 그 칸을 새 결과로 갱신 (항목 수 그대로)",
          t.get(A)[:3] == (1, LOWER, 55) and t.get(D)[2] == 44 and len(t) == 2)
    t.new_search()
    t.store(E, 1, EXACT, 66, None)
    check("새 세대: 이전 세대의 깊은 항목(D, 깊이 9)도 얕은 새 결과에 첫째 칸을 내줌",
          t.slots[2 * (A % nb)][4] == E and t.get(D)[2] == 44 and t.get(A) is None and len(t) == 2)
    other = 6
    check("다른 버킷은 영향 없음 / 없는 국면 조회는 None", t.get(other) is None and len(t) == 2)
    z = TranspositionTable(0)
    z.store(A, 5, EXACT, 1, None)
    check("용량 0: 저장은 무시, 조회는 항상 None", len(z) == 0 and z.get(A) is None)

    # 실제 탐색에서의 세대: 두 번째 탐색이 첫 탐색의 항목을 덮어쓸 수 있음
    s = Searcher(tt_size=64)
    s.search(Board(KIWI), max_depth=3, on_info=None)
    g1 = s.tt.generation
    s.search(Board(START_FEN), max_depth=3, on_info=None)
    gens = {e[5] for e in s.tt.slots if e is not None}
    check("search() 호출마다 세대 +1, 작은 표에서는 새 탐색 항목이 옛 항목을 밀어냄",
          s.tt.generation == g1 + 1 and (g1 + 1) in gens and len(s.tt) <= 64, f"세대 {sorted(gens)}")

    # 메이트 점수는 '그 국면에서 메이트까지의 거리'로 저장되어, 다른 ply에서 꺼내도 정확
    krk = "7k/8/8/1R5K/8/8/8/8 w - - 0 1"
    s = Searcher(tt_size=1000)
    mv, sc = s.search(Board(krk), max_depth=5, on_info=None)
    b = Board(krk)
    b.make_move(mv)
    child = s.tt.get(b.hash)                     # 최선수 뒤 흑 차례 국면 (ply 1): 루트 기준 -(MATE-3)
    check("KRK #2: 최선수 뒤 국면(ply 1)의 TT 점수 = '그 국면에서 2 ply 뒤 메이트당함' -(MATE-2), "
          "ply 1에서 꺼내면 -(MATE-3), ply 3에서 꺼내면 -(MATE-5)",
          sc == MATE - 3 and child is not None and child[1] == EXACT and child[2] == -(MATE - 2)
          and _from_tt(child[2], 1) == -(MATE - 3) and _from_tt(child[2], 3) == -(MATE - 5),
          f"{format_score(sc)} {child[:3] if child else None}")

MATE_SET = [
    ("Rd8#", "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", MATE - 1),
    ("Rxe8+ #2", "3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1", MATE - 3),
    ("KQK #2", "4K2k/8/8/3Q4/8/8/8/8 w - - 0 1", MATE - 3),
    ("KRK #2", "7k/8/8/1R5K/8/8/8/8 w - - 0 1", MATE - 3),
    ("f8=N#", POS_A, MATE - 1),
    ("f8=R! #2", POS_D, MATE - 3),
    ("흑 f1=N#", POS_E, MATE - 1),
    ("흑 f1=R! #2", POS_E3, MATE - 3),
]


def test_v041_tt_correctness():
    section("v0.4.1-5  TT 크기가 결과의 정확성을 바꾸지 않음")
    ok, detail = True, []
    for name, fen, want in MATE_SET:
        got = []
        for cap in (0, 2, 16, 1000, 300_000):
            mv, sc = Searcher(tt_size=cap).search(Board(fen), max_depth=5, on_info=None)
            got.append(sc)
        good = all(g == want for g in got)
        ok &= good
        if not good:
            detail.append(f"{name}: {got}")
    check("메이트 8국면 × TT 용량 0·2·16·1000·30만: 메이트 거리가 모두 같음 (작은 표에서 밀려나도 거리 정확)",
          ok, ' '.join(detail))

    ok, detail = True, []
    for name, fen, judge in (("나이트 포크", "4k3/7p/q7/1N6/8/8/P6P/4K3 w - - 0 1", {"b5c7"}),
                             ("공짜 퀸", "4k3/8/8/3q4/8/8/8/3QK3 w - - 0 1", {"d1d5"}),
                             ("지금 퀸 승격", POS_B1, {"e7e8q"})):
        for cap in (0, 16, 300_000):
            mv, _ = Searcher(tt_size=cap).search(Board(fen), max_depth=4, on_info=None)
            good = mv.uci() in judge
            ok &= good
            if not good:
                detail.append(f"{name}/{cap}:{mv.uci()}")
    check("전술 3국면 × TT 용량 0·16·30만: 모두 정답", ok, ' '.join(detail))

    # 이력 의존 무승부 점수는 작은 표에서도 재사용하지 않음 (기존 v0.3.1 테스트의 작은 표 버전)
    b = Board('4k3/8/8/8/8/8/8/R3K3 w - - 0 1')
    for mv in "e1d1 e8d7 d1e1 d7e8 e1d1 e8d7 d1e1".split():
        b.push_uci(mv)
    s = Searcher(tt_size=16)
    s.search(b, max_depth=4, on_info=None)
    warm = s.search(Board(b.fen()), max_depth=4, on_info=None)[1]
    cold = Searcher(tt_size=0).search(Board(b.fen()), max_depth=4, on_info=None)[1]
    check("용량 16: 반복 무승부(0점)를 본 뒤 이력 없는 같은 국면 = TT 없이 탐색한 점수 (지는 점수)",
          warm == cold and warm < -300, f"warm {warm}, cold {cold}")


KS_POSITIONS = {
    "안전한 캐슬링 킹": "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7",
    "중앙 노출 킹": "r1b1r1k1/ppp1qppp/2n2n2/2b5/8/2N2N2/PPP2PPP/R1BQKB1R w KQ - 0 1",
    "무너진 실드": "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N1P/PPP2P2/R1BQ1RK1 w - - 0 7",
    "룩·퀸 공격": "r1b3rk/pppp3p/2n2n2/2b1p3/2B1P2q/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7",
    "교환된 종반": "8/5pk1/6p1/8/8/6P1/5PK1/8 w - - 0 1",
    "킹 중앙 활동 종반": "8/p4p2/1p2k3/8/8/1P2K3/P4P2/8 w - - 0 1",
}


def ks_side(b, c):
    """색 c 킹의 안전 점수 (그 킹 쪽에서 본 값, 0 이하) — 항목별 기준 구현에서"""
    import evaluate as E
    return E.king_safety_detail(b)[c]['total']


def ref_king_attack(b, k, enemy):
    """독립 기준 구현: 킹 구역의 각 칸에서 '거꾸로' 나이트·비숍·룩 움직임을 쏴서 공격자를 찾음
    (evaluate.py의 빠른 경로는 상대 기물에서 구역 쪽으로 걸어가는 방식 + 미리 계산한 표)."""
    from board import KNIGHT_STEPS, BISHOP_DIRS, ROOK_DIRS, KING_STEPS
    units = {'N': 2, 'B': 2, 'R': 3, 'Q': 5}
    bd = b.board
    zone = [k] + [k + d for d in KING_STEPS if bd[k + d] != ' ']
    mine = (lambda p: p.isupper()) if enemy == WHITE else (lambda p: p.islower())
    found = set()
    for z in zone:
        for d in KNIGHT_STEPS:
            p = bd[z + d]
            if p in 'Nn' and mine(p):
                found.add(z + d)
        for dirs, kinds in ((BISHOP_DIRS, 'BQ'), (ROOK_DIRS, 'RQ')):
            for d in dirs:
                t = z + d
                while bd[t] == EMPTY:
                    t += d
                p = bd[t]
                if p != ' ' and p.upper() in kinds and mine(p):
                    found.add(t)
    return sum(units[bd[s].upper()] for s in found), len(found)


@with_ks(True)
def test_v041_king_safety():
    section("v0.4.1-6  King Safety (폰 실드·열린 파일·킹 공격, 중반 전용) — 기대값은 v0.4.2 공식 기준")
    # v0.4.2에서 공식이 바뀌어(수비 기물 반영, 열린 파일의 룩·퀸) 손으로 계산한 기대값 2개가 달라짐:
    #   중앙 노출 킹 -103 → -64,  룩·퀸 공격 -150 → -73.  나머지 검사 방식은 그대로 (정확한 값 비교).
    import evaluate as E
    P = {k: Board(v) for k, v in KS_POSITIONS.items()}
    w = {k: ks_side(b, WHITE) for k, b in P.items()}
    check("안전한 캐슬링 킹(g1, f2·g2·h2, 공격자 1개): 0",
          w["안전한 캐슬링 킹"] == 0, f"{w['안전한 캐슬링 킹']}")
    check("무너진 실드(g 폰 없음 -20, h3 -10, g파일 반쯤 열림 -8): -38, 안전한 킹보다 낮음",
          w["무너진 실드"] == -38 < w["안전한 캐슬링 킹"], f"{w['무너진 실드']}")
    check("중앙 노출 킹(e1): d·e 열린 파일 -30, e파일에 퀸 -10, Qe7+Bc5 공격 7 − 수비 min(6, 3) = 4 → -24: 합 -64",
          w["중앙 노출 킹"] == -64, f"{w['중앙 노출 킹']}")
    check("룩·퀸 공격(Qh4+Rg8+Bc5 = 10, 수비 3 → 7² × 3/2): -73, 무너진 실드만 있는 킹보다 낮음",
          w["룩·퀸 공격"] == -73 and w["룩·퀸 공격"] < w["무너진 실드"], f"{w['룩·퀸 공격']}")

    ok = True
    for name in ("교환된 종반", "킹 중앙 활동 종반"):
        b = P[name]
        terms, _, _ = E.eval_terms(b)
        with ks_mode(False):
            off = E.evaluate_white(b)
        ok &= terms['킹 안전'] == (0, 0) and E.evaluate_white(b) == off
    end = P["킹 중앙 활동 종반"]
    center_bonus = E.evaluate_white(end) - E.evaluate_white(Board("8/p4p2/1p2k3/8/8/1P6/P4P2/6K1 w - - 0 1"))
    check("퀸 없는 종반 2국면: 킹 안전 0, 평가 = 끈 상태와 같음 / 종반엔 백 킹 e3가 g1보다 높게 평가 (킹 활동)",
          ok and center_bonus > 0,
          f"e3 - g1 = {center_bonus:+d}")

    # 대칭: 색을 바꾼 국면은 부호만 바뀜 (6국면 + 무작위 2400국면)
    fens = list(KS_POSITIONS.values()) + random_positions(60, 40, 5)
    bad = sum(evaluate_white(Board(f)) != -evaluate_white(mirror(Board(f))) for f in fens)
    bad_ks = 0
    for f in fens:
        b = Board(f)
        t1 = E.eval_terms(b)[0]['킹 안전'][0]
        t2 = E.eval_terms(mirror(b))[0]['킹 안전'][0]
        bad_ks += t1 != -t2
    check(f"대칭: {len(fens)}국면에서 평가·킹 안전 항목 모두 색을 바꾸면 부호만 바뀜", bad == 0 and bad_ks == 0,
          f"평가 {bad}, 킹 안전 {bad_ks}")

    # 빠른 구현(미리 계산한 표 + 기물에서 걸어가기) = 독립 기준 구현(구역에서 거꾸로 쏘기)
    diff = n_att = 0
    for f in fens:
        b = Board(f)
        for c in (WHITE, BLACK):
            enemy = [(s, b.board[s].upper()) for s in range(120) if b.board[s] in ('nbrq' if c == WHITE else 'NBRQ')]
            got = E._king_attack(b.board, b.king_sq[c], enemy)
            ref = ref_king_attack(b, b.king_sq[c], c ^ 1)
            diff += got != ref
            n_att += ref[1] >= 2
    check(f"킹 공격 계산: {len(fens) * 2}개 킹에서 독립 기준 구현과 단위·공격자 수가 모두 같음",
          diff == 0 and n_att > 100, f"불일치 {diff}, 공격자 2개 이상 {n_att}번")

    # 크기: 한쪽 킹 안전의 이론상 최솟값 = 실드 3×(-20) + 파일 3×(-15-10) + 공격 상한 -250 = -385
    #       (v0.4.1은 -355. v0.4.2에서 '열린 파일에 상대 룩·퀸' 항목 3×(-10)이 더해짐)
    worst = min(min(ks_side(Board(f), WHITE), ks_side(Board(f), BLACK)) for f in fens)
    terms = [E.eval_terms(Board(f))[0]['킹 안전'][0] for f in fens]
    avg = sum(abs(t) for t in terms) / len(terms)
    check("가중치 크기: 한쪽 최저점이 이론 한계 -385 이상, 무작위 국면 평균 |킹 안전| < 100cp",
          worst >= -385 and avg < 100, f"최저 {worst}, 평균 |값| {avg:.0f}")

    # 상대 공격력이 부족하면(기물 하나 이하) 계산하지 않음 → 끈 평가와 같음
    #   (v0.4.1의 검사는 '퀸이 없으면 같음'이었음. v0.4.2는 퀸이 없어도 룩·경량 기물의 공격을 보도록 바뀌어
    #    조건이 '양쪽 공격력 < 4'로 바뀜. 퀸 없는 공격 국면은 test_v042_king_safety의 D에서 확인)
    same = True
    n_low = 0
    for f in fens + [fen for _, fen in ENDGAME_FENS]:
        b = Board(f)
        pw = [d['power'] for d in E.king_safety_detail(b)]
        if max(pw) < E.KS_MIN_POWER:
            n_low += 1
            with ks_mode(False):
                off = E.evaluate_white(b)
            same &= E.evaluate_white(b) == off
    check("양쪽 공격력이 4 미만(기물 하나 이하)인 국면: 켬/끔 평가가 같음", same and n_low >= 5, f"{n_low}국면")


ENDGAME_FENS = [
    ("폰 종반", "6k1/p4p2/1p6/8/8/1P6/P4P2/6K1 w - - 0 1"),
    ("폰 종반 (킹 중앙)", "8/p4p2/1p2k3/8/8/1P2K3/P4P2/8 w - - 0 1"),
    ("룩 종반", "3r4/5pk1/6p1/8/8/6P1/5PK1/3R4 w - - 0 1"),
    ("나이트 대 비숍", "8/5pk1/6p1/3b4/8/4N1P1/5PK1/8 w - - 0 1"),
    ("퀸 종반", "8/5pk1/6p1/3q4/8/4Q1P1/5PK1/8 w - - 0 1"),
    ("KRK", "7k/8/8/1R5K/8/8/8/8 w - - 0 1"),
]

KS_CASES = {   # 이름: (FEN, 백 킹의 기대 내역 일부)
    "B1 공격자 1개 (퀸)": ("6k1/5ppp/8/8/7q/8/5PPP/3R2K1 w - - 0 1", 0),
    "B2 공격자 2개 (퀸+비숍)": ("6k1/5ppp/8/2b5/7q/8/5PPP/3R2K1 w - - 0 1", -54),
    "B3 공격자 3개 (퀸+비숍+룩), g폰 없음": ("6k1/5ppp/8/2b5/7q/6r1/5P1P/3R2K1 w - - 0 1", -144),
    "C1 실드 무너짐, 상대는 나이트 하나": ("6k1/5ppp/8/8/8/2n5/5P2/3R2K1 w - - 0 1", 0),
    "C2 실드 무너짐, 상대는 룩 하나": ("3r2k1/5ppp/8/8/8/8/5P2/3R2K1 w - - 0 1", 0),
    "C3 열린 g파일, 상대는 퀸 하나 (룩 없음, 공격자 1)": ("6k1/5p1p/8/8/8/8/1q3P1P/1Q4K1 w - - 0 1", 0),
    "D1 퀸 없음: 룩 둘 (2랭크 + g파일)": ("6k1/5ppp/8/8/8/6r1/r4P1P/3R2K1 w - - 0 1", -51),
    "D2 퀸 없음: 룩 + 비숍": ("6k1/5ppp/8/2b5/8/6r1/5P1P/3R2K1 w - - 0 1", -24),
    "D3 퀸 없음: 룩 + 나이트": ("6k1/5ppp/8/8/8/5nr1/5P1P/3R3K w - - 0 1", -24),
    "수비 3개 (Rf1·Be2·Nf3) vs 퀸+비숍": ("r4rk1/ppp2ppp/8/2b5/7q/5N2/PPPQBPPP/5RK1 w - - 0 1", -24),
    "수비 1개 vs 퀸+비숍": ("r4rk1/ppp2ppp/8/2b5/7q/8/PPP2PPP/R5K1 w - - 0 1", -54),
    "열린 g파일에 상대 룩 + 퀸": ("6rk/5p1p/8/8/8/8/1q3P1P/1Q3K2 w - - 0 1", -113),
}


@with_ks(True)
def test_v042_king_safety():
    section("v0.4.2-2  King Safety 개정 (공격력 기준·수비 기물·퀸 없는 공격) — 요청서 7. A~F")
    import contextlib
    import io
    import evaluate as E
    got = {k: ks_side(Board(f), WHITE) for k, (f, _) in KS_CASES.items()}
    bad = {k: (got[k], want) for k, (_, want) in KS_CASES.items() if got[k] != want}
    check(f"손으로 계산한 기대값과 일치 ({len(KS_CASES)}국면, 백 킹의 킹 안전 점수)", not bad, f"{bad or ''}")

    # A. 색상 대칭 (새 국면들 + 종반)
    fens = [f for f, _ in KS_CASES.values()] + [f for _, f in ENDGAME_FENS]
    asym = [f for f in fens if evaluate_white(Board(f)) != -evaluate_white(mirror(Board(f)))
            or ks_side(Board(f), WHITE) != ks_side(mirror(Board(f)), BLACK)]
    check("A. 대칭: 색을 바꾸면 평가는 부호만, 백 킹의 점수 = 뒤집은 국면의 흑 킹 점수", not asym, f"{asym or ''}")

    # B. 공격이 늘면 위험이 커짐 (합리적인 범위 안에서)
    b1, b2, b3 = got["B1 공격자 1개 (퀸)"], got["B2 공격자 2개 (퀸+비숍)"], got["B3 공격자 3개 (퀸+비숍+룩), g폰 없음"]
    check("B. 공격자 1개 0 > 2개 -54 > 3개(+실드 손상) -144, 모두 상한 -385 이내",
          b1 == 0 > b2 > b3 >= -385, f"{b1} / {b2} / {b3}")
    check("B. 수비 기물이 많으면 같은 공격(퀸+비숍)의 벌점이 줄어듦: 수비 1개 -54 → 수비 3개 -24 (0이 되지는 않음)",
          got["수비 1개 vs 퀸+비숍"] < got["수비 3개 (Rf1·Be2·Nf3) vs 퀸+비숍"] < 0)

    # C. 공격 기물이 부족하면 폰 구조가 무너져도 벌점 없음
    c = [got[k] for k in KS_CASES if k.startswith('C')]
    check("C. 실드가 무너졌어도 상대 기물이 나이트 하나·룩 하나·퀸 하나뿐이면 0 (v0.4.1 공식은 퀸 하나만 있어도 열린 g파일 국면에 -35)",
          c == [0, 0, 0], f"{c}")

    # D. 퀸이 없는 공격
    d = [got[k] for k in KS_CASES if k.startswith('D')]
    with ks_mode(False):
        off = [evaluate_white(Board(KS_CASES[k][0])) for k in KS_CASES if k.startswith('D')]
    on = [evaluate_white(Board(KS_CASES[k][0])) for k in KS_CASES if k.startswith('D')]
    check("D. 퀸 없이 룩 둘 / 룩+비숍 / 룩+나이트가 킹 구역을 공격: 벌점 발생 (v0.4.1은 퀸이 없어 0), "
          "평가도 끈 상태보다 낮음", all(x < 0 for x in d) and all(a < b for a, b in zip(on, off)),
          f"킹 안전 {d}, 평가 끔 {off} → 켬 {on}")
    check("D. 열린 파일: 상대에게 룩·퀸이 그 파일에 있으면 추가 벌점 (실드·파일·룩 -80 × 공격력 8/16 = -40, 공격 -73)",
          E.king_safety_detail(Board(KS_CASES["열린 g파일에 상대 룩 + 퀸"][0]))[WHITE]['structure'] == -40)

    # E. 종반: 킹 활동을 막지 않음
    same_eval = True
    same_move = []
    for name, fen in ENDGAME_FENS:
        with ks_mode(False):
            e_off = evaluate_white(Board(fen))
            m_off = quiet_search(Board(fen), max_depth=4)
        same_eval &= evaluate_white(Board(fen)) == e_off
        m_on = quiet_search(Board(fen), max_depth=4)
        same_move.append(m_on == m_off)
    mv, _ = quiet_search(Board(ENDGAME_FENS[0][1]), max_depth=5)
    k_from = Board(ENDGAME_FENS[0][1]).king_sq[WHITE]
    check("E. 종반 6국면(폰·룩·경량 기물·퀸 하나): 평가와 깊이 4 탐색 결과(수·점수)가 끈 상태와 같음",
          same_eval and all(same_move), f"{same_move}")
    check("E. 폰 종반에서 킹(g1)을 중앙 쪽으로 움직이는 수를 고름 (King Safety 켬)",
          mv.frm == k_from and mv.uci() in ('g1f1', 'g1g2', 'g1f2'), mv.uci())
    r_center = evaluate_white(Board("3r4/5pk1/6p1/8/3K4/6P1/5P2/3R4 w - - 0 1"))
    r_corner = evaluate_white(Board("3r4/5pk1/6p1/8/8/6P1/5PK1/3R4 w - - 0 1"))
    rb = evaluate_white(Board("3r4/5pk1/6p1/3b4/8/2N1K1P1/5P2/3R4 w - - 0 1")) \
        - evaluate_white(Board("3r4/5pk1/6p1/3b4/8/2N3P1/5PK1/3R4 w - - 0 1"))
    check("E. 룩 종반·룩+경량 기물 종반에서도 중앙의 킹을 구석의 킹보다 높게 평가",
          r_center > r_corner and rb > 0, f"룩 종반 {r_center - r_corner:+d}, 룩+경량 {rb:+d}")

    # F. 끔/켬 차이를 항목별로 출력
    board = Board(KS_CASES["B3 공격자 3개 (퀸+비숍+룩), g폰 없음"][0])
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        off_v, on_v = E.explain_king_safety(board, "B3")
    text = buf.getvalue()
    w, bl = E.king_safety_detail(board)
    _, phase, _ = E.eval_terms(board)
    check("F. explain_king_safety: 끔→켬 차이 = (백 합 − 흑 합) × phase/24, 실드·열린 파일·공격자·수비 항목 출력",
          on_v - off_v == E.taper(w['total'] - bl['total'], 0, phase) and w['total'] == -144
          and all(t in text for t in ('실드', '열린 파일', '공격자', '수비', '상대 공격력')),
          f"{off_v} → {on_v}")
    check("F. 내역의 합이 맞음: 폰 구조 + 공격 = 합, 폰 구조 = (실드+파일+룩·퀸) × min(공격력,16)/16",
          all(d['structure'] + d['attack'] == d['total'] and
              d['structure'] == -(-(d['shield'] + d['files'] + d['heavy_on_file']) * min(d['power'], 16) // 16)
              for f in fens for d in E.king_safety_detail(Board(f))))


def test_v042_fast_eval():
    section("v0.4.2-1  평가 최적화: 빠른 경로 = 항목별 기준 경로, 폰 캐시")
    import evaluate as E
    fens = random_positions(60, 40, 5) + random_positions(40, 80, 9) + list(KS_POSITIONS.values()) \
        + [f for f, _ in KS_CASES.values()] + [f for _, f in ENDGAME_FENS]
    for flag in (False, True):
        with ks_mode(flag):
            bad = sum(E.evaluate_white(Board(f)) != E.evaluate_white_terms(Board(f)) for f in fens)
        check(f"King Safety {'켬' if flag else '끔'}: {len(fens)}국면에서 빠른 경로 = 항목별로 따로 계산해 합친 값",
              bad == 0, f"불일치 {bad}")
    # 폰 캐시: 비워도, 가득 차서 비워져도 값이 같고, 크기 한도를 넘지 않음
    with ks_mode(True):
        want = [E.evaluate_white(Board(f)) for f in fens]
        E.clear_pawn_cache()
        cold = [E.evaluate_white(Board(f)) for f in fens]
        saved = E.PAWN_CACHE_MAX
        try:
            E.PAWN_CACHE_MAX = 50
            E.clear_pawn_cache()
            peak = 0
            small = []
            for f in fens:
                small.append(E.evaluate_white(Board(f)))
                peak = max(peak, len(E._PAWN_CACHE))
        finally:
            E.PAWN_CACHE_MAX = saved
            E.clear_pawn_cache()
    check("폰 캐시: 비운 뒤에도, 한도 50으로 줄여 계속 비워지게 해도 값이 같음 / 항목 수가 한도를 넘지 않음",
          cold == want and small == want and peak <= 50, f"최대 {peak}개")
    # 같은 폰 배치에서 킹만 옮기면 킹 칸별로 따로 기억 (다른 킹 칸의 값이 섞이지 않음)
    with ks_mode(True):
        E.clear_pawn_cache()
        a = "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N1P/PPP2P2/R1BQ1RK1 w - - 0 7"
        b2 = "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N1P/PPP2P2/R1BQ1R1K w - - 0 7"
        v = [E.evaluate_white(Board(x)) for x in (a, b2, a, b2)]
        t = [E.evaluate_white_terms(Board(x)) for x in (a, b2)]
    check("폰 캐시: 폰 배치가 같고 킹 칸만 다른 두 국면을 번갈아 평가해도 각각 맞는 값",
          v == t + t and len(E._PAWN_CACHE) == 1, f"{v}")


def _G_CASES():
    rep = Board('4k3/8/8/8/8/8/8/R3K3 w - - 0 1')
    for mv in "e1d1 e8d7 d1e1 d7e8 e1d1 e8d7 d1e1".split():
        rep.push_uci(mv)
    return [   # (이름, Board를 만드는 함수, 기대 점수 또는 None, 허용 수 집합 또는 None, 금지 수 집합)
        ("1수 메이트 Qxf7#", lambda: Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4"), MATE - 1, None, ()),
        ("1수 메이트 Rd8#", lambda: Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"), MATE - 1, {"d1d8"}, ()),
        ("흑 승격 메이트 b1=Q#", lambda: Board("6k1/5ppp/8/8/8/8/1p3PPP/6K1 b - - 0 1"), MATE - 1, None, ()),
        ("가장 빠른 메이트 #2 (Rxe8+)", lambda: Board("3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1"), MATE - 3, {"e2e8"}, ()),
        ("가장 빠른 메이트 #2 (KQK)", lambda: Board("4K2k/8/8/3Q4/8/8/8/8 w - - 0 1"), MATE - 3, None, ()),
        ("지는 쪽: 가장 늦은 메이트 (-#1)", lambda: Board("3qR1k1/5ppp/8/8/8/8/5PPP/4R1K1 b - - 0 1"), -(MATE - 2), {"d8e8"}, ()),
        ("언더프로모션 f8=N#", lambda: Board(POS_A), MATE - 1, {"f7f8n"}, ()),
        ("언더프로모션 exf8=N#", lambda: Board(POS_C), MATE - 1, {"e7f8n"}, ()),
        ("퀸 승격은 스테일메이트 → f8=R (#2)", lambda: Board(POS_D), MATE - 3, {"f7f8r"}, ()),
        ("흑 언더프로모션 f1=N#", lambda: Board(POS_E), MATE - 1, {"f2f1n"}, ()),
        ("스테일메이트 함정 (Nxa1 금지)", lambda: Board("7k/5K1p/7P/8/8/1N6/2PP4/b7 w - - 0 1"), None, None, ("b3a1",)),
        ("50수 청구 가능해도 메이트", lambda: Board("7k/6pp/8/7N/8/8/8/6QK w - - 100 1"), MATE - 1, {"g1g7"}, ()),
        ("지는 쪽은 50수 청구가 되는 수", lambda: Board("6k1/6pp/8/7N/8/8/8/6QK b - - 99 1"), 0, {"g8h8", "g8f8", "g8f7"}, ()),
        ("75수째라도 메이트가 우선", lambda: Board("7k/6pp/8/7N/8/8/8/6QK w - - 149 1"), MATE - 1, {"g1g7"}, ()),
        ("3회 반복으로 비기기 (룩 없는 흑)", lambda: rep, 0, {"d7e8"}, ()),
    ]


def test_v042_search_with_ks():
    section("v0.4.2-3  평가를 바꿔도 탐색 기능 유지 (King Safety 켬/끔 모두) — 요청서 7. G")
    for flag in (True, False):
        bad = []
        with ks_mode(flag):
            for name, make, want, allowed, banned in _G_CASES():
                b = make()
                before = state_of(b)
                mv, sc = quiet_search(b, max_depth=4)
                ok = (want is None or sc == want) and (allowed is None or mv.uci() in allowed) \
                    and mv.uci() not in banned and state_of(b) == before
                if not ok:
                    bad.append(f"{name}: {mv.uci()} {format_score(sc)}")
            # 알파베타 = 창 없는 탐색: 깊이 3에서 전체 창 negamax 값과 search 점수가 같음
            ab = []
            for fen in (KIWI, TESTS[5][1], KS_POSITIONS["룩·퀸 공격"]):
                s1 = Searcher(tt_size=0)
                _, sc = s1.search(Board(fen), max_depth=3, on_info=None)
                s2 = Searcher(tt_size=0)
                s2.root_len = 0
                full = s2.negamax(Board(fen), 3, -INF, INF, 0)
                ab.append(sc == full)
        check(f"King Safety {'켬' if flag else '끔'}: 메이트·빠른 메이트·늦은 패배·언더프로모션·스테일메이트·50수·75수·"
              f"반복 15국면 모두 기대한 수와 점수, 상태 복구", not bad, '; '.join(bad))
        check(f"King Safety {'켬' if flag else '끔'}: 반복 심화 결과 = 전체 창 negamax 값 (3국면, 깊이 3)", all(ab), f"{ab}")



def test_quick_basics():
    section("빠른 기본 점검: 합법수(perft)·해시·make/unmake·UCI 기본 명령")
    # perft: 6개 국면에서 노드 2만 이하인 깊이 (합법수 생성, 캐슬링·앙파상·승격 포함)
    bad = []
    for name, fen, counts in TESTS:
        for d, want in counts.items():
            if want <= 20000 and perft(Board(fen), d) != want:
                bad.append(f"{name} d{d}")
    check("perft 정답 (6개 국면, 노드 2만 이하 깊이)", not bad, ' '.join(bad))
    # 무작위 대국 20판 × 60수: 수를 둘 때마다 해시 = 처음부터 계산한 해시, 전부 무르면 처음 상태
    rng = random.Random(42)
    hash_bad = restore_bad = 0
    for g in range(20):
        b = Board(([START_FEN] + [f for _, f, _ in TESTS])[g % 7])
        start = state_of(b)
        n = 0
        for _ in range(60):
            moves = b.legal_moves()
            if not moves:
                break
            b.make_move(rng.choice(moves))
            n += 1
            hash_bad += b.hash != b.compute_hash()
        for _ in range(n):
            b.unmake_move()
        restore_bad += state_of(b) != start
    check("무작위 대국 20판: 매 수 뒤 Zobrist 해시 = 처음부터 계산한 값, 전부 무르면 처음 상태 그대로",
          hash_bad == 0 and restore_bad == 0, f"해시 {hash_bad}, 복구 {restore_bad}")
    # UCI 기본 명령 (엔진을 프로세스로 띄워서)
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        p = subprocess.run([sys.executable, os.path.join(here, 'uci.py')], capture_output=True, text=True, timeout=60,
                           input="uci\nisready\nucinewgame\nposition startpos moves e2e4 e7e5\ngo depth 3\n"
                                 "position fen 6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1\ngo depth 2\nquit\n")
        out = p.stdout.splitlines()
        best = [l.split()[1] for l in out if l.startswith('bestmove')]
        b = Board()
        b.push_uci('e2e4')
        b.push_uci('e7e5')
        ok = ('uciok' in out and 'readyok' in out and len(best) == 2 and best[1] == 'd1d8'
              and best[0] in [m.uci() for m in b.legal_moves()] and any('score mate 1' in l for l in out))
        detail = ' '.join(best)
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    check("UCI: uci/isready/position/go/quit — uciok, readyok, 합법 bestmove, 1수 메이트는 'score mate 1'과 Rd8", ok, detail)


GROUPS = [
    ('v0.3.1', (test_problem1_check_in_quiescence, test_problem2_stalemate_in_quiescence,
                test_problem3_mate_scores, test_ep_hash, test_repetition_fifty,
                test_insufficient_material, test_search_interruption, test_abnormal_input,
                test_regression)),
    ('v0.3.2', (test_v032_delta_pruning, test_v032_draw_rules, test_v032_terminal_search,
                test_v032_state_restore, test_v032_play_cli)),
    ('v0.3.3', (test_v033_A_knight_mate, test_v033_B_queen_promo, test_v033_C_capture_underpromo,
                test_v033_D_stalemate_avoid, test_v033_E_black, test_v033_F_windows,
                test_v033_G_state, test_v033_extra, test_v033_horizon, test_v033_play_cli)),
    ('v0.4.1', (test_v041_root_moves, test_v041_node_limit, test_v041_tt_capacity,
                test_v041_tt_replacement, test_v041_tt_correctness, test_v041_king_safety)),
    ('v0.4.2', (test_quick_basics, test_v042_fast_eval, test_v042_king_safety, test_v042_search_with_ks)),
]
# --quick: 같은 테스트 함수 가운데 빨리 끝나는 것만 고른 부분집합 (조건은 전체 테스트와 똑같음)
#   빠진 것(전체에서만): 무작위 국면 대량 검증, 노드 한도·TT 용량 반복 탐색, 자체 대국 등 오래 걸리는 9개
QUICK = (test_quick_basics,                                             # 합법수·해시·make/unmake·UCI 기본
         test_problem2_stalemate_in_quiescence, test_ep_hash, test_repetition_fifty,
         test_insufficient_material, test_search_interruption, test_abnormal_input,
         test_v032_draw_rules, test_v032_terminal_search, test_v032_state_restore, test_v032_play_cli,
         test_v033_A_knight_mate, test_v033_B_queen_promo, test_v033_C_capture_underpromo,
         test_v033_D_stalemate_avoid, test_v033_E_black, test_v033_F_windows, test_v033_horizon,
         test_v033_play_cli,                                            # 승격·언더프로모션·스테일메이트
         test_v041_tt_replacement, test_v041_tt_correctness,
         test_v041_king_safety, test_v042_fast_eval, test_v042_king_safety,   # 평가 대칭·대표 국면
         test_v042_search_with_ks)                                      # 메이트·무승부 규칙 (KS 켬/끔)


def run_tests(mode='full', show_times=False):
    t0 = time.time()
    quick = {f.__name__ for f in QUICK}
    ran, not_run, times = [], [], []
    for name, tests in GROUPS:
        GROUP[0] = name
        for test in tests:
            if mode == 'quick' and test.__name__ not in quick:
                not_run.append(test.__name__)
                continue
            t = time.time()
            test()
            times.append((time.time() - t, test.__name__))
            ran.append(test.__name__)
    print()
    for name, _ in GROUPS:
        rows = [r for r in RESULTS if r[0] == name]
        if rows:
            print(f"{name} 테스트: {len(rows)}개 중 {sum(r[2] for r in rows)}개 통과")
    failed = [n for g, n, ok in RESULTS if not ok]
    label = '빠른 회귀 테스트 (--quick)' if mode == 'quick' else '전체 테스트 (--full)'
    print(f"[{label}] 실행 {len(RESULTS)}개: 통과 {len(RESULTS) - len(failed)}, 실패 {len(failed)}, "
          f"건너뜀 {len(SKIPPED)}  ({time.time() - t0:.0f}s, 테스트 함수 {len(ran)}개 실행"
          + (f", {len(not_run)}개는 --full에서만 실행" if not_run else '') + ")")
    if show_times:
        for dt, n in sorted(times, reverse=True):
            print(f"  {dt:6.1f}s  {n}")
    if SKIPPED:
        print(f"건너뜀 {len(SKIPPED)}개 (통과로 세지 않음):", *[n for _, n in SKIPPED], sep='\n  ')
    if failed:
        print("실패:", *failed, sep='\n  ')
        raise SystemExit(1)


if __name__ == '__main__':
    # python test_engine.py           전체 (기존과 같음)
    # python test_engine.py --full    전체
    # python test_engine.py --quick   빠른 회귀 테스트
    # --times 를 붙이면 테스트 함수별 걸린 시간을 보여 줌
    run_tests('quick' if '--quick' in sys.argv else 'full', '--times' in sys.argv)
