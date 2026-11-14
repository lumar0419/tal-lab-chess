"""
search.py — 3단계: 탐색

"내가 이렇게 두면 상대는 최선으로 이렇게 받고, 그러면 나는…"을 몇 수 앞까지 따져
가장 좋은 수를 고릅니다. 평가함수(2단계)는 '지금 국면'만 보고, 탐색이 '앞날'을 봅니다.

이 파일에 들어간 기법 (위에서 아래로 쌓아 올리는 순서)

 1) 네가맥스(negamax)  미니맥스를 한 함수로 쓴 것. "상대에게 최선 = 나에게 최악"이므로
                        상대 점수에 마이너스를 붙이면 백·흑을 같은 코드로 처리할 수 있음.
 2) 알파베타 가지치기   "이미 이것보다 나쁜 게 확정된 수는 끝까지 볼 필요 없다."
                        결과는 미니맥스와 똑같고, 보는 노드 수만 크게 줄어듦.
    + PVS (v0.4.9) 첫 합법 수는 전체 창으로, 후속 수는 1cp 창으로 먼저 시험.
                          alpha를 넘되 beta 미만이면 전체 창으로 재탐색. 기본 ON.
    + Aspiration (v0.4.10, 실험) 지난 깊이의 정확한 점수 ±80cp 창으로 먼저 탐색.
                          창을 벗어나면 반드시 전체 창으로 재탐색. 기본 OFF.
 3) 정적 탐색(quiescence)  깊이가 끝나도 '잡는 수'는 끝까지 따라가 봄.
                        퀸으로 폰을 잡은 직후에 멈추면, 다음 수에 퀸이 잡히는 걸 못 봄.
                        · 체크를 받은 국면에서는 '멈추고 평가'(stand pat)를 하지 않고 모든 체크
                          회피 수를 봄. 회피 수가 없으면 체크메이트.
                        · 체크가 아니고 둘 수가 없으면 스테일메이트(0점). 평가값으로 컷하기 전에 확인.
                        · 승격은 퀸·룩·비숍·나이트 4종 모두 봄 (v0.3.3).
                        · v0.4.3: 실험 옵션 TacticalChecks 활성화 시 정적 탐색 첫 층에서만
                          잡지 않는 체크(quiet check)도 검토. 기본 OFF — 속도/실력 확인 전.
                        · 델타 가지치기(가망 없어 보이는 잡기 생략)는 기본적으로 끔 (v0.3.2).
                          '현재 평가 + 잡는 기물 값 + 여유분'은 실제 결과의 상한이 아니라서
                          (잡으면서 체크→메이트, 통과폰, 기물 부족, 스테일메이트 등) 메이트를 놓침.
                          대신 각 잡기 뒤의 정적 탐색이 자기 평가값으로 바로 컷하므로,
                          가망 없는 잡기는 평가 한 번으로 정확하게 정리됨.
 4) 수 정렬              좋은 수를 먼저 볼수록 알파베타가 더 많이 잘라 냄.
                        ① 지난번 탐색의 최선수(TT) ② 잡는 수: 비싼 것을 싼 것으로(MVV-LVA)
                        ③ 킬러 수: 같은 깊이에서 가지치기를 일으켰던 조용한 수 ④ 히스토리 점수
 5) 트랜스포지션 테이블(TT)  다른 수순으로 같은 국면에 오면 저장해 둔 결과를 재사용.
                        열쇠는 board.hash (Zobrist 해시).
                        v0.4.1부터 고정 크기 표(버킷당 2칸: 깊이 우선 + 항상 교체, 세대 표시):
                        탐색 도중에도 tt_size를 넘지 않음 (TranspositionTable 설명 참고).
 6) 반복 심화           깊이 1, 2, 3 …으로 늘려 가며 탐색. 시간이 다 되면 마지막으로 완료한
                        깊이의 답을 냄. 얕은 탐색 결과가 TT에 남아 다음 깊이의 수 정렬을 도와서
                        오히려 한 번에 깊게 보는 것보다 빠를 때가 많음.
                        멈춤 조건(v0.4.1): 시간·정지 신호는 1024노드마다, 노드 한도는 정확히 그 수에서.
                        루트 후보 제한(root_moves, UCI go searchmoves)도 지원.
 + 체크 연장           체크를 받은 국면은 한 수 더 깊게 봄 (메이트 수순을 놓치지 않게)

점수: 센티폰. 메이트는 ±(MATE − 루트에서 메이트까지의 수(ply)).
      이기는 쪽은 빠른 메이트일수록 점수가 크고, 지는 쪽은 늦은 메이트일수록 점수가 큼
      → 자연스럽게 '가장 빠른 메이트'와 '최대한 버티기'를 고름.

무승부 처리 (v0.3.2 — 실제 규칙은 board.outcome / claimable_draw 와 같은 기준)
  [실제 규칙: 자동 무승부]  75수 규칙, 5회 동형반복, 스테일메이트, 기물 부족 → 0점으로 끝.
      단 75수째 수가 메이트면 메이트가 우선 (FIDE 9.6.2).
  [실제 규칙: 청구 가능]   50수 규칙, 3회 동형반복 → '0점으로 끝낼 권리'로 취급.
      · 그 국면에서 둘 차례인 쪽: 청구(0점)와 계속 두기 중 나은 쪽 = max(0, 계속 둔 값).
        그래서 청구할 수 있어도 즉시 메이트가 있으면 메이트를 고름.
      · 그 국면을 만든 수를 둔 쪽: '이 수를 두면서' 청구할 수 있음 (FIDE 9.2.1.1, 9.3.1).
        양쪽 모두 0점을 확보할 수 있으므로 그런 수의 가치는 정확히 0점 (그 수가 메이트가 아니면).
        → 부모 노드에서 수를 둔 직후 바로 판정하고, 그 아래는 더 탐색하지 않음 (빠름).
  [탐색용 근사]  탐색 트리 안에서 같은 국면이 한 번 더 나오면 → 0점.
      실제 규칙상 아직 청구할 수 없지만, 같은 수순을 되풀이하면 결국 3회째에 청구할 수 있다는
      가정. 대부분의 엔진이 쓰는 방식이며, 한쪽이 되풀이 대신 더 나은 수를 가진 경우 달라질 수 있음.
  루트 국면 자체의 청구 여부는 탐색이 아니라 호출하는 쪽(play.py, 4단계 UCI)이 점수를 보고 결정.

TT와 대국 이력 (graph history interaction)
  같은 해시라도 '어떤 수순으로 왔는가'(반복 이력, halfmove)에 따라 점수가 달라질 수 있습니다.
  · 하위 탐색에서 반복·50수·75수 규칙이 한 번이라도 적용된 노드는 점수를 저장하지 않고
    수 정렬용 최선수만 저장 (점수가 이력에 의존하므로).
  · halfmove가 100에 가까워 50수 규칙이 탐색 범위 안에 들어올 수 있으면 TT 점수를 쓰지 않음.
  · 남는 한계: 이력과 무관하게 저장된 점수를 '지금의 이력에서는 반복으로 비길 수 있는' 국면에
    재사용할 수는 있음. 이걸 완전히 없애려면 TT를 거의 못 쓰게 되어 대부분의 엔진도 감수함.
"""

import time
from collections import Counter
from typing import NamedTuple, List

from board import (Board, Move, EMPTY, START_FEN, H_HASH, SQUARES, WHITE,
                   file_of, rank_of)
from evaluate import evaluate

INF = 1_000_000
MATE = 100_000
MATE_BOUND = MATE - 1_000      # 이보다 절댓값이 크면 '메이트 점수'
MAX_PLY = 100

from version import VERSION as ENGINE_VERSION

EXACT, LOWER, UPPER, MOVE_ONLY = 0, 1, 2, 3   # TT 종류: 정확한 값 / 이 이상 / 이 이하 / 점수 없음
TT_HALFMOVE_MARGIN = 10        # 체크 연장 등으로 실제 수순이 깊이보다 길어질 수 있는 여유분

AUTO, CLAIM = 'auto', 'claim'  # 무승부 규칙 종류: 0점으로 끝 / 둘 차례인 쪽이 청구 가능

# 시간·정지 신호는 이 노드 수마다 확인 (time.monotonic() 호출을 줄이려고). 노드 한도는 v0.4.1부터
# 이 간격과 무관하게 정확히 지킴: 다음 확인 시점을 '한도'보다 늦지 않게 잡음.
CHECK_INTERVAL = 1024

# 수 정렬용 기물 가치 (킹으로 잡는 수는 가장 마지막에)
ORDER_VALUE = {'.': 0}
for _p, _v in zip('PNBRQK', (100, 320, 330, 500, 900, 1000)):
    ORDER_VALUE[_p] = ORDER_VALUE[_p.lower()] = _v


# ── v0.8.8 선택적 탐색(SelectiveSearch)용 상수 ──
# 깊이 단위는 반수. 여유값은 centipawn. 전부 '탐색을 줄이는' 장치이므로 기본은 꺼져 있고
# Searcher.selective = True 일 때만 쓰인다. 캡처·승격·체크는 본탐색에서 줄이거나 버리지 않는다.
RFP_MAX_DEPTH = 3              # 역 futility: 정적 평가가 beta보다 이만큼*깊이 이상 높으면 컷
RFP_MARGIN = 120
FUTILITY_MARGIN = (0, 200, 350)     # 남은 깊이 1, 2에서 조용한 수를 건너뛰는 여유값
LMP_COUNT = (0, 6, 10, 16)          # 남은 깊이 1~3에서 이 개수 뒤의 조용한 수는 건너뜀
QS_DELTA = 200                      # 정적 탐색: 잡아도 alpha에 이만큼 못 미치면 건너뜀
SAC_MIN = 100                       # 이만큼 이상 기물을 내준 수순을 '희생 뒤 수순'으로 본다
import math as _math
LMR_TABLE = [[0] * 64 for _ in range(64)]
for _d in range(1, 64):
    for _n in range(1, 64):
        LMR_TABLE[_d][_n] = int(0.75 + _math.log(_d) * _math.log(_n) / 2.25)


# ── v0.9.3 전술 프로필 ──
# 선택적 탐색(같은 시간에 더 깊이) 위에 '기물을 내주는 수는 더 깊이 본다'는 연장을 얹은 묶음.
# 값은 evidence/v093 의 같은 시간 비교에서 고른 것이며 Searcher.set_tactical()이 적용한다.
TACTICAL_PROFILE = {'selective': True, 'sac_extension': 2}
_TACTICAL_OFF = {'sac_extension': 0}


class TimeUp(Exception):
    """시간·노드 한도 초과 또는 정지 요청 → 탐색을 즉시 중단"""


class SearchInfo(NamedTuple):
    depth: int
    score: int
    nodes: int
    seconds: float
    pv: List[Move]   # 예상 수순 (principal variation)


def mate_plies(score):
    """메이트 점수 → 루트에서 메이트까지 남은 수(ply). 메이트 점수가 아니면 None"""
    if score > MATE_BOUND:
        return MATE - score
    if score < -MATE_BOUND:
        return MATE + score
    return None


def format_score(score):
    """사람이 읽는 점수: '+0.35' / '#3'(3수 안에 메이트시킴) / '#-2'(2수 뒤 메이트당함) / '#0'(메이트당한 상태)"""
    plies = mate_plies(score)
    if plies is None:
        return f"{score / 100:+.2f}"
    if score > 0:
        return f"#{(plies + 1) // 2}"
    return f"#-{plies // 2}" if plies else "#0"


def uci_score(score):
    """UCI 형식 점수 (4단계에서 사용)"""
    plies = mate_plies(score)
    if plies is None:
        return f"cp {score}"
    if score > 0:
        return f"mate {(plies + 1) // 2}"
    return f"mate -{plies // 2}" if plies else "mate 0"


def _to_tt(score, ply):
    """메이트 점수는 '루트에서 몇 수'가 아니라 '이 국면에서 몇 수'로 바꿔 저장"""
    if score > MATE_BOUND:
        return score + ply
    if score < -MATE_BOUND:
        return score - ply
    return score


def _from_tt(score, ply):
    """저장된 '이 국면에서 몇 수'를 지금 탐색의 '루트에서 몇 수'로 되돌림"""
    if score > MATE_BOUND:
        return score - ply
    if score < -MATE_BOUND:
        return score + ply
    return score


def print_info(info: SearchInfo):
    nps = int(info.nodes / info.seconds) if info.seconds > 0 else 0
    pv = ' '.join(m.uci() for m in info.pv)
    print(f"깊이 {info.depth:>2}  점수 {format_score(info.score):>7}  "
          f"노드 {info.nodes:>9,}  {info.seconds:6.2f}s  {nps:>6,}/s  수순 {pv}")


class TranspositionTable:
    """고정 크기 트랜스포지션 테이블 (v0.4.1).

    v0.4.0까지는 파이썬 dict였고, 크기 확인은 탐색을 시작할 때만 해서 탐색 도중에는 얼마든지 커질 수
    있었음. 이제는 처음에 '용량'만큼 칸을 만들어 두고 그 안에서만 저장 → 용량을 넘을 수 없음.

    구조: 해시값으로 고른 '버킷'마다 칸 2개
      첫째 칸 (깊이 우선)  깊게 탐색한 결과를 오래 보존. 새 결과가 더 깊거나 같을 때, 또는 지금 칸의
                          항목이 이전 탐색(이전 세대)에서 남은 것일 때만 차지하고, 밀려난 항목은 둘째 칸으로.
      둘째 칸 (항상 교체)  그 외의 새 결과는 여기에 → 최근 결과가 들어갈 자리가 항상 있음.
      같은 국면이 이미 있으면 그 칸을 새 결과로 바꿈 (v0.4.0 dict와 같은 동작).
    세대(generation): 탐색(search 호출)마다 1 증가. 이전 수를 생각할 때 저장한 깊은 항목이
                     첫째 칸을 영원히 차지하지 않게 함.
    비용: 저장·조회 모두 나머지 연산 1번과 비교 몇 번.

    항목: (깊이, 종류, 점수, 최선수, 해시, 세대) — 앞 4개는 v0.4.0 dict 값과 같은 순서라
          entry[1](종류), entry[3](최선수) 같은 기존 사용법이 그대로 통함.
    용량 0이면 TT를 쓰지 않음 (조회는 항상 없음, 저장은 무시)."""

    def __init__(self, capacity):
        self.generation = 0
        self.preserve_deeper = False
        self.resize(capacity)

    def resize(self, capacity):
        """용량(항목 수)을 바꿈. 내용은 비워짐."""
        self.capacity = max(0, int(capacity))
        self.nbuckets = self.capacity // 2
        self.slots = [None] * (self.nbuckets * 2)
        self.count = 0

    def clear(self):
        self.slots = [None] * (self.nbuckets * 2)
        self.count = 0

    def new_search(self):
        self.generation += 1

    def __len__(self):
        return self.count

    def get(self, key):
        """저장된 항목 (깊이, 종류, 점수, 최선수, 해시, 세대) 또는 None"""
        if not self.nbuckets:
            return None
        i = (key % self.nbuckets) << 1
        slots = self.slots
        e = slots[i]
        if e is not None and e[4] == key:
            return e
        e = slots[i + 1]
        if e is not None and e[4] == key:
            return e
        return None

    def store(self, key, depth, flag, score, move):
        if not self.nbuckets:
            return
        i = (key % self.nbuckets) << 1
        slots = self.slots
        gen = self.generation
        new = (depth, flag, score, move, key, gen)
        a = slots[i]
        if a is not None and a[4] == key:              # 같은 국면 → 갱신
            if not self.preserve_deeper or not self._prefer_existing(a, new):
                slots[i] = new
            return
        b = slots[i + 1]
        if b is not None and b[4] == key:
            if not self.preserve_deeper or not self._prefer_existing(b, new):
                slots[i + 1] = new
            return
        if a is None:                                   # 빈 첫째 칸
            slots[i] = new
            self.count += 1
        elif a[5] != gen or depth >= a[0]:              # 이전 세대이거나 새 결과가 같거나 더 깊음
            if b is None:
                self.count += 1
            slots[i + 1] = a                            # 밀려난 항목은 둘째 칸으로 (둘째 칸의 옛 항목은 버림)
            slots[i] = new
        else:                                           # 첫째 칸의 깊은 결과는 보존
            if b is None:
                self.count += 1
            slots[i + 1] = new

    @staticmethod
    def _prefer_existing(old, new):
        if old[1] == MOVE_ONLY:
            return False
        if new[1] == MOVE_ONLY:
            return True
        return old[0] > new[0] or (old[0] == new[0] and old[1] == EXACT and new[1] != EXACT)

    def __setitem__(self, key, value):                  # v0.4.0 dict 방식 저장과 호환: tt[key] = (깊이, 종류, 점수, 수)
        self.store(key, *value)

    def __contains__(self, key):
        return self.get(key) is not None


class Searcher:
    def __init__(self, tt_size=300_000):
        self.tt = TranspositionTable(tt_size)   # 고정 크기 (v0.4.1). 항목 수 기준 용량
        self.stop_requested = False  # 4단계 UCI 'stop' 명령이 이걸 True로 바꿈
        self.nodes = 0
        self.deadline = None
        self.node_limit = None
        self._next_check = CHECK_INTERVAL   # 이 노드 수에 도달하면 _check_limits() 호출
        self.root_filter = None      # go searchmoves: 루트에서 볼 수의 집합 (None이면 전부)
        self.root_len = 0            # 탐색 시작 시점의 board.history 길이 (반복 판정 기준선)
        self.draw_hits = 0           # 이력 의존 무승부(반복·50수)를 만난 횟수
        self.root_best = None
        self.pv_table = None
        self.cancel_check = None
        self.eval_cache_size = 16000
        self._eval_cache = None
        self.reuse_root_order = True
        self._root_hint = None
        self._tt_settings = None
        self._tt_history_context = None
        self.tt_current_generation_only = False
        self.killers = [[None, None] for _ in range(MAX_PLY + 2)]
        self.history = {}
        # 정적 탐색의 근사 델타 가지치기. v0.3.2부터 기본값 False (메이트를 놓칠 수 있어서).
        # 비교·실험용으로만 남겨 둠: True로 켜면 v0.3.1과 같은 근사 가지치기를 함 (정확성 보장 없음).
        self.delta_pruning = False
        # Experimental tactical extension: include quiet checking moves at the first
        # quiescence ply. Disabled until paired games show a benefit; togglable via UCI.
        # A single quiet-check ply keeps the branching factor bounded.
        self.qsearch_quiet_checks = False
        # v0.4.4: 거친 '체크 가능성' 사전 판정으로 불필요한 make/unmake를 줄임.
        # 실험·교차 검증 시 False로 바꿔 원래 정확한 전수 검사와 직접 비교할 수 있음.
        self.qsearch_fast_checks = True
        # v0.4.9: Principal Variation Search (PVS). 첫 번째 합법 수는 전체 탐색 창,
        # 이후 수는 1cp 너비의 null-window로 시험하고 alpha를 넘는 경우만 전체 재탐색.
        # 고정 깊이 회귀 테스트에서 동일한 점수와 더 적은 탐색 비용을 확인하여 기본 ON.
        self.pvs = True
        self.pvs_probes = 0
        self.pvs_researches = 0
        # v0.4.10: 좁은 aspiration 창으로 후속 반복 심화를 먼저 탐색.
        # 창 밖으로 벗어나면 전체 창으로 반드시 재탐색: 실험 옵션, 기본 OFF.
        self.aspiration = False
        self.aspiration_window = 80  # centipawns, fixed window around last completed score
        self.aspiration_probes = 0
        self.aspiration_researches = 0
        self.aspiration_fail_low = 0
        self.aspiration_fail_high = 0
        # v0.4.11 experimental move-ordering-only king pressure / quiet checks.
        # Never drops moves or changes their evaluation. Kept OFF until benchmarked.
        self.tactical_ordering = False
        self.tactical_order_nodes = 0
        self.tactical_order_candidates = 0
        # Experimental second quiet checking move along a forcing quiescence line.
        # Requires TacticalChecks, remains OFF by default to avoid qsearch explosion.
        self.check_continuation = False
        self.qsearch_capture_bridge = False
        # A bounded research profile. A quiet check is extended only when
        # the defender has at most this many legal evasions (zero disables it).
        self.qsearch_forcing_replies = 0
        self.check_continuation_nodes = 0
        # Conservative experimental late-move reductions (non-PV, quiet, non-checking
        # alternatives only). All tactical moves still receive full depth.
        self.fast_evasions = True  # exact candidate filter, no search reduction
        self.lmr = False
        self.lmr_probes = 0
        self.lmr_researches = 0
        # None preserves the original extension on every checked node.
        self.check_extension_limit = None
        self.null_move_pruning = False
        self.null_threat_extension = False
        self.null_probes = self.null_cutoffs = self.null_threats = 0
        self._after_null = False
        # v0.8.8 선택적 탐색. selective가 꺼져 있으면 아래 항목은 전혀 쓰이지 않고
        # 탐색은 v0.8.7과 같은 전폭(full-width) 탐색이다. 개별 스위치는 비교 실험용.
        self.selective = False
        self.sel_qsearch = True      # 정적 탐색: SEE로 손해인 캡처와 가망 없는 캡처를 건너뜀
        self.sel_null = True         # null-move 가지치기 (R = 2 + 깊이/4)
        self.sel_rfp = True          # 역 futility 가지치기
        self.sel_futility = True     # futility + late move pruning (조용하고 체크 아닌 수만)
        self.sel_lmr = True          # late move reductions (로그 표, 재탐색 포함)
        self.sel_iir = True          # TT 수가 없는 깊은 노드는 1반수 얕게
        self.sel_order = True        # SEE로 손해인 캡처를 킬러 뒤로 정렬
        # 희생 뒤 수순 보호: 루트에서 이 반수 안쪽에서는, 기물을 내준 쪽의 조용한 후속 수를
        # 줄이거나 버리지 않고, 기물을 받은 쪽을 '평가가 좋다'는 이유만으로 컷하지 않는다.
        self.sel_sac_ply = 3
        self.sel_sac_root_only = True
        self.sel_qchecks = True      # 정적 탐색 첫 층에서 조용한 체크도 본다 (TacticalChecks와 같은 동작)
        self.sel_stats = Counter()
        self.selective_trace = None  # Optional research callback (event, board, ply, depth, move).
        # v0.9.3 희생 수 연장: 루트에서 기물을 내주는 수(SEE <= -SAC_MIN)를 이 반수만큼 더 깊이 본다.
        # 가지를 버리지 않고 더 보는 장치라 시간이 더 든다. 기본 0(꺼짐), set_tactical()이 켠다.
        self.sac_extension = 0
        self.ext_stats = Counter()
        self._gain = [0] * (MAX_PLY + 3)
        self.tactical = False        # set_tactical()로 켠 상태인지 (표시용)

    def set_tactical(self, enabled=True):
        """v0.9.3 전술 프로필을 켜거나 끈다.

        켜면 TACTICAL_PROFILE의 값을 적용한다 (선택적 탐색 포함). 끄면 v0.9.3 연장만 기본값으로
        되돌리고 selective는 건드리지 않는다 — 부르는 쪽이 원래 설정을 다시 넣는다."""
        if enabled:
            for key, value in TACTICAL_PROFILE.items():
                setattr(self, key, value)
        elif self.tactical:
            for key in TACTICAL_PROFILE:
                if key in _TACTICAL_OFF:
                    setattr(self, key, _TACTICAL_OFF[key])
        self.tactical = bool(enabled)

    @property
    def tt_size(self):
        """TT 용량(항목 수). 바꾸면 TT를 그 크기로 새로 만듦 (내용은 비워짐)."""
        return self.tt.capacity

    @tt_size.setter
    def tt_size(self, capacity):
        self.tt.resize(capacity)

    # ──────────────────────────── 바깥에서 부르는 함수 ────────────────────────────
    def search(self, board: Board, max_depth=MAX_PLY, time_limit=None, node_limit=None,
               on_info=print_info, root_moves=None, min_depth=1, on_iteration=None,
               full_time=False, multipv=1, on_multipv=None, cancel_check=None, mate_stop=None):
        """반복 심화. (최선수, 점수)를 돌려줌. time_limit은 초 단위.

        반환 규칙 (v0.3.2)
          체크메이트(둘 차례인 쪽이 메이트당함)          → (None, -MATE)
          스테일메이트, 자동 무승부(기물 부족·75수·5회 반복) → (None, 0)
          대국 진행 중                                    → (최선수, 점수)
          ※ 50수·3회 반복처럼 '청구 가능'한 국면은 아직 끝난 게 아니므로 수를 돌려줌.
            청구 여부는 호출하는 쪽이 점수를 보고 결정 (점수 < 0 이면 청구가 유리).
        root_moves (v0.4.1, UCI go searchmoves): 루트에서 이 수들만 후보로 봄 (Move 또는 'e2e4').
          불법수는 무시하고, 남는 후보가 없으면 (None, 0). 루트 아래는 평소처럼 모든 수를 봄.
        node_limit: 정확히 이 노드 수에서 멈춤 (v0.4.1).
        mate_stop: optional positive or negative mate-score confirmation callback (move, score, plies).
        멈추면 마지막으로 끝낸 깊이의 최선수, 깊이 1도 못 끝냈으면 그때까지의 최선 또는 첫 합법수.
        multipv=1은 이전과 완전히 같은 단일 최선수 탐색. multipv=2~5는
        이전 순위를 루트에서 제외해 재탐색하므로, 각각 서로 다른 실제 루트 후보
        점수를 반환합니다. on_multipv에 SearchInfo 목록을 각 *완료된* 깊이마다
        전달합니다. 계산 도중 일부 후보만 끝나면 그 깊이는 게시하지 않습니다.
        탐색이 시간 초과·정지·예외로 끊겨도 board는 호출 전 상태 그대로 돌아옵니다."""
        if type(min_depth) is not int or not 1 <= min_depth <= max_depth:
            raise ValueError('min_depth must be between 1 and max_depth')
        if type(multipv) is not int or not 1 <= multipv <= 5:
            raise ValueError('multipv must be an integer from 1 to 5')
        self.nodes = 0
        self.start = time.monotonic()
        self.deadline = self.start + time_limit if time_limit else None
        self.node_limit = node_limit
        interval = self._check_interval()
        self._next_check = min(interval, node_limit) if node_limit else interval
        self.stop_requested = False
        self.root_filter = None
        self.cancel_check = cancel_check
        self.pv_table = [()] * (MAX_PLY + 2) if (on_info or on_multipv) else None
        self.killers = [[None, None] for _ in range(MAX_PLY + 2)]
        self.history = {}
        self.draw_hits = 0
        self.pvs_probes = 0
        self.pvs_researches = 0
        self.aspiration_probes = 0
        self.aspiration_researches = 0
        self.aspiration_fail_low = 0
        self.aspiration_fail_high = 0
        self.tactical_order_nodes = 0
        self.tactical_order_candidates = 0
        self.check_continuation_nodes = 0
        self.lmr_probes = 0
        self.lmr_researches = 0
        self.null_probes = self.null_cutoffs = self.null_threats = 0
        self.root_len = len(board.history)
        import evaluate as evaluation
        settings = (self.qsearch_quiet_checks, self.check_continuation, self.qsearch_capture_bridge,
                    self.qsearch_forcing_replies, self.delta_pruning,
                    self.pvs, self.aspiration, self.aspiration_window, self.tactical_ordering,
                    self.lmr, self.check_extension_limit, self.null_move_pruning,
                    self.null_threat_extension, evaluation.ATTACK_ACTIVITY, evaluation.INITIATIVE,
                    evaluation.KING_SAFETY, self.selective, self.sel_qsearch, self.sel_null,
                    self.sel_rfp, self.sel_futility, self.sel_lmr, self.sel_iir, self.sel_order,
                    self.sel_sac_ply, self.sel_sac_root_only, self.sel_qchecks,
                    self.sac_extension)
        # Scores from a different reversible game history can hide future draw
        # claims even when no draw was visited in the cached search. The board
        # hash intentionally excludes the halfmove clock and game history.
        # Preserve warm TT reuse for the identical analysis request; start with
        # fresh scores when that draw context changes. Internal tree repetition
        # remains the documented search approximation.
        history_context = (board.halfmove, tuple(
            h[H_HASH] for h in board.history[max(0, len(board.history)-board.halfmove):]))
        if ((self._tt_settings is not None and self._tt_settings != settings) or
                (self._tt_history_context is not None and self._tt_history_context != history_context)):
            self.tt.clear()
        self._tt_settings = settings
        self._tt_history_context = history_context
        self._eval_cache = {} if self.eval_cache_size else None
        self._eval_cache_limit = self.eval_cache_size * (8 if self.selective else 1)
        self._gain[0] = 0
        self.sel_stats.clear()
        self.ext_stats.clear()
        self.tt.new_search()           # 세대 증가: 이전 탐색의 항목은 교체 우선 대상이 됨

        state = board.snapshot()
        try:
            ended = board.outcome()        # 이미 규칙상 자동으로 끝난 국면이면 수를 내지 않음
            if ended is not None:
                return None, (0 if ended[0] == '1/2-1/2' else -MATE)

            candidates = board.legal_moves()
            if root_moves is not None:      # go searchmoves: 지정한 수 중 합법수만 후보로
                wanted = {m if isinstance(m, Move) else str(m).strip().lower() for m in root_moves}
                candidates = [m for m in candidates if m in wanted or m.uci() in wanted]
                if not candidates:
                    return None, 0
                self.root_filter = frozenset(candidates)

            if multipv > 1:
                # An exact full-window root search is repeated for each line,
                # excluding the already selected root moves. Each selected line
                # is independently searched (not a score from move ordering).
                # The entire group must finish before a depth is published.
                return self._multi_pv_loop(board, candidates, multipv, max_depth,
                                           min_depth, full_time, on_info,
                                           on_iteration, on_multipv, state)

            best_move, best_score = None, 0
            for depth in range(1, max_depth + 1):
                self.root_best = None
                try:
                    if on_iteration is not None:
                        on_iteration(depth)
                    self._check_limits()
                    # v0.4.10: 마지막으로 *완료한* 깊이의 정확한 평가를 중심으로
                    # aspiration window를 시도한다. fail-low/high는 경계값이므로
                    # 반드시 전체 창으로 재탐색한다. 특히 메이트 점수는 좁히지 않는다.
                    if (self.aspiration and depth > 1 and best_move is not None
                            and abs(best_score) < MATE_BOUND):
                        radius = max(1, int(self.aspiration_window))
                        lo = max(-INF, best_score - radius)
                        hi = min(INF, best_score + radius)
                        self.aspiration_probes += 1
                        score = self.negamax(board, depth, lo, hi, 0)
                        if score <= lo or score >= hi:
                            if score <= lo:
                                self.aspiration_fail_low += 1
                            else:
                                self.aspiration_fail_high += 1
                            self.aspiration_researches += 1
                            self.root_best = None
                            score = self.negamax(board, depth, -INF, INF, 0)
                    else:
                        score = self.negamax(board, depth, -INF, INF, 0)
                except TimeUp:
                    board.restore(state)            # 탐색 도중 상태 → 즉시 원래대로
                    if best_move is None:           # 깊이 1도 못 끝냈으면 그때까지 찾은 최선
                        best_move = self.root_best
                    break
                best_move, best_score = self.root_best, score
                elapsed = time.monotonic() - self.start
                if on_info:
                    on_info(SearchInfo(depth, score, self.nodes, elapsed,
                                       list(self.pv_table[0])))
                plies = mate_plies(score)
                if (plies is not None and plies <= depth
                        and (mate_stop is None or mate_stop(best_move, score, plies))):
                    break  # 이 깊이 안에서 메이트가 확정 → 더 볼 필요 없음
                if (self.deadline and not full_time and depth >= min_depth
                        and elapsed > (self.deadline - self.start) * 0.5):
                    break  # 최소 목표 깊이 이후에만 조기 종료 (절대 시간 제한은 그대로 적용)
            if best_move is None:
                best_move = candidates[0]           # 깊이 1도 못 끝냄 → 합법적인 대체 수
            return best_move, best_score
        finally:
            board.restore(state)                    # 어떤 예외가 나도 국면은 원래대로
            self.root_filter = None
            self.pv_table = None
            self.cancel_check = None
            self._root_hint = None
            self._eval_cache = None

    def _multi_pv_loop(self, board, candidates, multipv, max_depth, min_depth,
                       full_time, on_info, on_iteration, on_multipv, state):
        """Exact root-level MultiPV at each *completed* depth.

        The kth search excludes the previous k-1 winners at the root. All
        subtrees are searched with the normal engine/TT and a full alpha-beta
        window. Root scores are never entered into the TT with a restricted
        root_filter (as enforced by negamax), because they are not the value
        of the unrestricted position. A partially completed group is discarded.
        """
        allowed = frozenset(candidates)
        needed = min(multipv, len(candidates))
        best_move, best_score = None, 0
        previous = []
        for depth in range(1, max_depth + 1):
            found = set()
            lines = []
            try:
                if on_iteration is not None:
                    on_iteration(depth)
                for _ in range(needed):
                    self._check_limits()
                    self.root_filter = allowed - found
                    if self.reuse_root_order:
                        self._root_hint = next((move for move in previous if move not in found), None)
                    self.root_best = None
                    score = self.negamax(board, depth, -INF, INF, 0)
                    move = self.root_best
                    if move is None or move in found:
                        raise RuntimeError('MultiPV root candidate missing')
                    found.add(move)
                    elapsed = time.monotonic() - self.start
                    pv = list(self.pv_table[0]) if self.pv_table is not None else [move]
                    lines.append(SearchInfo(depth, score, self.nodes, elapsed, pv))
            except TimeUp:
                board.restore(state)
                # Incomplete sets must not overwrite any completed depth.
                break
            # Heuristic search, TT reuse and path-dependent draw handling can
            # occasionally shift a later forced-root score relative to the
            # unrestricted first pass. Rank by the evaluated score rather
            # than assuming the selection order is already sorted.
            lines.sort(key=lambda line: line.score, reverse=True)
            previous = [line.pv[0] for line in lines]
            best_move, best_score = previous[0], lines[0].score
            if on_info is not None:
                on_info(lines[0])
            if on_multipv is not None:
                on_multipv(lines)
            if (self.deadline and not full_time and depth >= min_depth and
                    time.monotonic() - self.start > (self.deadline - self.start) * 0.5):
                break
        if best_move is None:
            best_move = candidates[0]
        return best_move, best_score

    # ──────────────────────────── 탐색 본체 ────────────────────────────
    def negamax(self, b: Board, depth, alpha, beta, ply, check_rules=True,
                checks_left=None, threat_left=True):
        self.nodes += 1
        if self.nodes >= self._next_check:          # 노드 한도는 정확히, 시간·정지는 일정 간격으로
            self._check_limits()
        root = ply == 0
        pv_node = beta - alpha > 1
        pv = self.pv_table if pv_node else None
        if self.pv_table is not None:
            self.pv_table[ply] = ()
        in_check = b.in_check()
        draw_hits_before = self.draw_hits

        # 무승부 규칙 확인. 탐색 내부에서는 부모가 수를 둔 직후 이미 확인했으므로
        # check_rules=False 로 불리고, 바깥에서 이 국면을 직접 부를 때만 여기서 확인함.
        if check_rules and not root:
            kind = self._rule_kind(b)
            if kind is not None:
                self.draw_hits += 1
                if b.halfmove >= 100 and in_check and not b.has_legal_move(in_check=True):
                    return -MATE + ply                 # 메이트는 50·75수 규칙보다 우선
                if kind == AUTO:
                    return 0
                # 청구 가능: 둘 차례인 쪽은 max(청구 0점, 계속 둔 값)을 고름
                if beta <= 0:
                    return 0                           # 청구만으로 이미 beta 이상
                return max(0, self.negamax(b, depth, max(alpha, 0), beta, ply,
                                           check_rules=False, checks_left=checks_left,
                                           threat_left=threat_left))

        # Budget counts extra full-search plies. Quiescence still searches
        # legal evasions even after that budget reaches zero.
        if root and checks_left is None:
            checks_left = self.check_extension_limit
        if in_check and checks_left != 0:
            depth += 1
            if checks_left is not None:
                checks_left -= 1
        if depth <= 0:
            return self.quiesce(b, alpha, beta, ply, in_check=in_check, check_rules=False)
        if ply >= MAX_PLY:
            return self._score_at_ply_limit(b, ply, in_check)

        sel = self.selective
        sac_ply = self.sel_sac_ply
        invested = -self._gain[ply] if sel and ply <= sac_ply else 0
        protection = invested
        if protection and self.sel_sac_root_only and (protection > 0) == (ply % 2 == 1):
            protection = 0
        trace = self.selective_trace

        # ── 트랜스포지션 테이블 조회 ──
        alpha_orig = alpha
        tt_move = None
        # Identical boards can have different remaining extension budgets.
        tt_key = b.hash
        if checks_left is not None:
            tt_key ^= (checks_left + 1) * 0x9E3779B97F4A7C15
        if self.null_threat_extension and not threat_left:
            tt_key ^= 0xD1B54A32D192ED03
        entry = None if self._after_null else self.tt.get(tt_key)
        # Near the root, identical positions can carry different remaining
        # protection budgets and material ledgers. Reuse their move only.
        protection_context = sel and 0 < ply <= sac_ply
        if entry is not None:
            e_depth, e_flag, e_score, tt_move = entry[0], entry[1], entry[2], entry[3]
            if (not root and not pv_node and not protection_context
                    and e_flag != MOVE_ONLY and e_depth >= depth
                    and (not self.tt_current_generation_only or entry[5] == self.tt.generation)
                    and b.halfmove + e_depth + TT_HALFMOVE_MARGIN < 100):
                s = _from_tt(e_score, ply)             # 충분히 깊게 본 결과면 그대로 사용
                if e_flag == EXACT:
                    return s
                if e_flag == LOWER and s >= beta:
                    return s
                if e_flag == UPPER and s <= alpha:
                    return s

        # ── v0.8.8 선택적 탐색: 수를 만들어 보기 전에 끝낼 수 있는 경우 ──
        static_eval = None
        if sel and not in_check:
            cache = self._eval_cache
            if cache is None:
                static_eval = evaluate(b)
            else:
                static_eval = cache.get(b.hash)
                if static_eval is None:
                    static_eval = evaluate(b)
                    if len(cache) < self._eval_cache_limit:
                        cache[b.hash] = static_eval
            if (not pv_node and not root and abs(beta) < MATE_BOUND and protection > -SAC_MIN
                    and b.halfmove + depth + TT_HALFMOVE_MARGIN < 100):
                # 역 futility: 이미 beta보다 넉넉히 좋으면 얕은 깊이에서는 더 보지 않는다.
                if (self.sel_rfp and depth <= RFP_MAX_DEPTH
                        and static_eval - RFP_MARGIN * depth >= beta
                        and b.has_legal_move(in_check=False)):
                    self.sel_stats['rfp'] += 1
                    if trace:
                        self._emit_trace(trace, 'rfp', b, ply, depth, None, alpha, beta, static_eval)
                    return static_eval - RFP_MARGIN * depth
                if (self.sel_null and not self._after_null and depth >= 3
                        and static_eval >= beta and self._has_null_material(b)):
                    self.sel_stats['null'] += 1
                    score = self._search_after_null(b, depth, beta, ply, checks_left,
                                                    reduction=3 + depth // 4)
                    if score >= beta:
                        if not b.has_legal_move(in_check=False):
                            return 0
                        self.sel_stats['null_cut'] += 1
                        if trace:
                            self._emit_trace(trace, 'null', b, ply, depth, None, alpha, beta, static_eval, probe_score=score)
                        return beta
            # TT 수가 없는 깊은 노드: 정렬 정보가 없으니 한 반수 얕게 본다 (다음 반복에서 채워짐).
            if self.sel_iir and tt_move is None and depth >= 4 and not root and abs(protection) < SAC_MIN:
                self.sel_stats['iir'] += 1
                if trace:
                    self._emit_trace(trace, 'iir', b, ply, depth, None, alpha, beta, static_eval, reduction=1)
                depth -= 1

        stored_depth = depth
        use_threat_probe = self.null_threat_extension and threat_left and depth >= 4
        if ((self.null_move_pruning or use_threat_probe) and not self._after_null
                and not root and not pv_node and not in_check and depth >= 3
                and abs(beta) < MATE_BOUND and b.halfmove + depth + TT_HALFMOVE_MARGIN < 100
                and (use_threat_probe or evaluate(b) >= beta)
                and self._has_null_material(b)):
            if (self.null_move_pruning and (not use_threat_probe or evaluate(b) >= beta)
                    and beta <= self._search_after_null(b, depth, beta, ply, checks_left) < MATE_BOUND):
                # Even a favorable pass cannot prove that a legal move exists.
                if not b.has_legal_move(in_check=False):
                    return 0
                self.null_cutoffs += 1
                return beta
            # A normal cp window can cut on an earlier non-mating move.
            if (use_threat_probe and self._search_after_null(
                    b, depth, 1 - MATE_BOUND, ply, checks_left) <= -MATE_BOUND):
                self.null_threats += 1
                depth += 1
                threat_left = False

        if root and self._root_hint is not None:
            tt_move = self._root_hint

        # ── 모든 수 시도 ──
        best_score, best_move = -INF, None
        legal = 0
        board = b.board
        moves = b.evasion_candidates() if in_check and self.fast_evasions else b.pseudo_legal_moves()
        sac_ext = self.sac_extension if root else 0
        if root and self.root_filter is not None:      # go searchmoves: 루트 후보만 남김 (아래 깊이는 전부)
            moves = [m for m in moves if m in self.root_filter]
        # Tactical ordering is limited to the upper tree and low remaining depths:
        # do not pay the geometric/check-candidate overhead at every leaf.
        priority_checks = None
        if self.tactical_ordering and ply <= 2 and not in_check and depth <= 4:
            priority_checks = set(self._quiet_check_candidates(b, moves=moves))
            self.tactical_order_nodes += 1
            self.tactical_order_candidates += len(priority_checks)
        # 선택적 탐색에서 '조용하고 체크가 아닌 수'만 줄이거나 건너뛴다. 체크 여부는 수를 두기 전에
        # 기하 후보 집합(과포함, 누락 없음)으로 판정한다: 집합에 없으면 확실히 체크가 아니다.
        sel_quiet = sel and not in_check and protection < SAC_MIN
        sel_prune = (sel_quiet and self.sel_futility and not pv_node and not root
                     and depth <= 3 and alpha > -MATE_BOUND
                     and b.halfmove + depth + TT_HALFMOVE_MARGIN < 100)
        sel_reduce = sel_quiet and self.sel_lmr and not root and depth >= 3
        track_gain = sel and ply < sac_ply
        lmr_from = 5 if pv_node else 3
        check_cands = None
        quiets_seen = 0
        for m in self.order_moves(b, moves, tt_move, ply, priority_checks):
            piece = board[m.frm]
            quiet = board[m.to] == EMPTY and not m.promo and not (
                m.to == b.ep and piece in 'Pp')
            reduction = 0
            if track_gain:
                self._gain[ply + 1] = invested - (
                    (ORDER_VALUE[board[m.to]] or (100 if piece in 'Pp' and m.to == b.ep else 0))
                    + (ORDER_VALUE[m.promo] - 100 if m.promo else 0))
            child_depth = depth - 1
            if sac_ext and b.see_estimate(m) <= -SAC_MIN:
                # v0.9.3 희생 수 연장: 루트에서 기물을 내주는 수는 보상이 늦게 드러나므로 더 깊이 본다.
                child_depth += sac_ext
                self.ext_stats['sac'] += 1
            prune = None
            quiet_candidate = (sel_prune or sel_reduce) and quiet and legal > 0
            if quiet_candidate:
                if check_cands is None:
                    check_cands = set(b.quiet_check_candidates())
                quiet_candidate = m not in check_cands and not (piece in 'Pp' and (
                    rank_of(m.to) >= 6 if piece == 'P' else rank_of(m.to) <= 1))
            b.make_move(m)
            if b.is_attacked(b.king_sq[b.side ^ 1], b.side):   # 내 킹이 체크에 남는 수 = 불법
                b.unmake_move()
                continue
            # Repetition takes at least four reversible plies, and the
            # move-count claims require a higher clock still.
            score = self._rule_child_score(b, ply) if b.halfmove >= 4 else None
            from_search = score is None
            if quiet_candidate and from_search:
                quiets_seen += 1
                if sel_prune and best_score > -MATE_BOUND and m != tt_move:
                    if quiets_seen > LMP_COUNT[depth]:
                        prune = 'lmp'
                    elif depth <= 2 and static_eval + FUTILITY_MARGIN[depth] <= alpha:
                        prune = 'futility'
                if prune:
                    self.sel_stats[prune] += 1
                    b.unmake_move()
                    if trace:
                        self._emit_trace(trace, prune, b, ply, depth, m, alpha, beta, static_eval)
                    continue
                if sel_reduce and legal + 1 >= lmr_from and m != tt_move:
                    reduction = LMR_TABLE[min(depth, 63)][min(legal + 1, 63)] - int(pv_node)
                    if m in self.killers[ply] or self.history.get((piece, m.to), 0) > depth * depth * 4:
                        reduction -= 1
                    reduction = min(reduction, depth - 2)
            legal += 1
            if from_search and reduction > 0:
                # 얕게 먼저 보고, alpha를 넘을 때만 아래에서 원래 깊이로 다시 본다.
                self.sel_stats['lmr'] += 1
                if trace:
                    self._emit_trace(trace, 'lmr', b, ply, depth, m, alpha, beta, static_eval, reduction=reduction, after_move=True)
                score = -self.negamax(b, child_depth - reduction, -alpha - 1, -alpha,
                                      ply + 1, False, checks_left, threat_left)
                if score > alpha:
                    self.sel_stats['lmr_research'] += 1
                    reduction = 0
            if from_search and reduction <= 0:
                # LMR reduces ONLY late quiet moves at non-PV nodes. Never reduce
                # captures, promotions, pawn pushes to the seventh, replies to check,
                # moves giving check, TT moves or killers. On a reduced fail-high,
                # always re-search at full depth. This is SELECTIVE: unlike PVS it
                # need not preserve full-width scores, so it is an opt-in experiment.
                do_lmr = (self.lmr and not sel and not root and not in_check and
                    depth >= 3 and legal >= 4 and beta - alpha == 1 and quiet and
                    m != tt_move and m not in self.killers[ply] and
                    self.history.get((piece, m.to), 0) < depth * depth * 4 and
                    not (piece in 'Pp' and (rank_of(m.to) >= 6 if piece == 'P' else rank_of(m.to) <= 1))
                    and not b.in_check())
                if do_lmr:
                    self.lmr_probes += 1
                    if trace:
                        self._emit_trace(trace, 'conservative_lmr', b, ply, depth, m,
                                         alpha, beta, static_eval, reduction=1, after_move=True)
                    score = -self.negamax(b, child_depth - 1, -alpha - 1, -alpha,
                                          ply + 1, False, checks_left, threat_left)
                    if score > alpha:
                        self.lmr_researches += 1
                        score = -self.negamax(b, child_depth, -beta, -alpha,
                                              ply + 1, False, checks_left, threat_left)
                elif self.pvs and legal > 1 and beta - alpha > 1:
                    # PVS: 첫 합법 수는 이미 전체 창에서 확인했다. 이후 수의 경우
                    # 기존 alpha를 넘을 수 있는지만 먼저 1cp 창으로 검사한다.
                    # null-window 값은 fail-soft 경계일 수 있으므로 alpha < score < beta면
                    # 전체 창으로 재탐색해야 정확한 점수와 PV를 구할 수 있다.
                    self.pvs_probes += 1
                    score = -self.negamax(b, child_depth, -alpha - 1, -alpha,
                                          ply + 1, False, checks_left, threat_left)
                    if alpha < score < beta:
                        self.pvs_researches += 1
                        score = -self.negamax(b, child_depth, -beta, -alpha,
                                              ply + 1, False, checks_left, threat_left)
                else:
                    score = -self.negamax(b, child_depth, -beta, -alpha,
                                          ply + 1, False, checks_left, threat_left)
            b.unmake_move()

            if score > best_score:
                best_score, best_move = score, m
                if root:
                    self.root_best = m
                if score > alpha:
                    if pv is not None:
                        pv[ply] = (m,) + (pv[ply + 1] if from_search else ())
                    alpha = score
                    if alpha >= beta:                  # 베타 컷: 상대가 이 국면을 허용하지 않음
                        if quiet and not self._after_null:
                            k = self.killers[ply]
                            if k[0] != m:
                                k[0], k[1] = m, k[0]
                            key = (piece, m.to)
                            self.history[key] = self.history.get(key, 0) + depth * depth
                        break

        if legal == 0:                                 # 둘 수가 없음
            return -MATE + ply if in_check else 0      # 체크메이트(거리 반영) / 스테일메이트

        if self._after_null or (root and self.root_filter is not None):
            pass        # Synthetic nodes and restricted roots have no reusable position score.
        elif self.draw_hits == draw_hits_before and not protection_context:
            flag = UPPER if best_score <= alpha_orig else LOWER if best_score >= beta else EXACT
            self.tt.store(tt_key, stored_depth, flag, _to_tt(best_score, ply), best_move)
        elif entry is None:
            self.tt.store(tt_key, 0, MOVE_ONLY, 0, best_move)
        return best_score

    def _emit_trace(self, callback, event, board, ply, depth, move, alpha, beta,
                    static_eval, **details):
        """Diagnostic allocation happens only with an explicitly enabled trace.

        Preserve the original five-argument research callback API. Structured
        recorders implement record() and receive the window and full context.
        """
        record = getattr(callback, 'record', None)
        if record is None:
            callback(event, board, ply, depth, move)
        else:
            record(event, board, ply, depth, move, alpha=alpha, beta=beta,
                   static_eval=static_eval, **details)

    @staticmethod
    def _has_null_material(board):
        pieces = 'NBRQ' if board.side == WHITE else 'nbrq'
        count = 0
        for square in SQUARES:
            if board.board[square] in pieces:
                count += 1
                if count == 2:
                    return True
        return False

    def _search_after_null(self, board, depth, beta, ply, checks_left, reduction=3):
        self.null_probes += 1
        draw_hits = self.draw_hits
        history_length = len(board.history)
        state = board.make_null_move()
        self._after_null = True
        saved_gain = self._gain[ply + 1]
        self._gain[ply + 1] = 0
        try:
            return -self.negamax(board, depth - reduction, -beta, 1 - beta, ply + 1,
                                 False, checks_left, False)
        finally:
            while len(board.history) > history_length:
                board.unmake_move()
            board.unmake_null_move(state)
            self._after_null = False
            self._gain[ply + 1] = saved_gain
            self.draw_hits = draw_hits

    def _quiet_check_candidates(self, b: Board, moves=None):
        """Filter quiet checks geometrically; the caller verifies king safety."""
        if self.qsearch_fast_checks:
            candidates = b.quiet_check_candidates()
            if moves is None:
                yield from candidates
            else:
                possible = set(candidates)
                yield from (move for move in moves if move in possible)
            return
        if moves is None:
            moves = b.pseudo_legal_moves()
        for move in moves:
            piece = b.board[move.frm]
            if b.board[move.to] == EMPTY and not move.promo and not (move.to == b.ep and piece in 'Pp'):
                yield move

    def quiesce(self, b: Board, alpha, beta, ply, in_check=None, check_rules=True,
                quiet_checks_left=None):
        """정적 탐색. 체크가 아니면 잡는 수·앙파상·승격(4종 모두)만, 체크면 모든 회피 수를 봄.
        in_check를 이미 알고 있으면 넘겨서 중복 계산을 피함.
        check_rules: 무승부 규칙 확인 여부 (탐색 내부에서는 부모가 이미 확인해서 False).
        quiet_checks_left: 이번 qsearch 가지에서 허용할 조용한 체크 횟수.
          기본 TacticalChecks에서는 1개만 허용. CheckContinuation이 켜지면
          조용한 체크→강제 회피→두 번째 조용한 체크를 1회 추가로 허용.
          캡처는 체크 예산을 소진합니다. 실험용 capture bridge는 체크 2회 예산을
          캡처 한 번 뒤 체크 1회로 바꿉니다.
        """
        if quiet_checks_left is None:
            quiet_checks_left = ((2 if self.check_continuation else 1)
                                 if self.qsearch_quiet_checks or (self.selective and self.sel_qchecks) else 0)
        self.nodes += 1
        if self.nodes >= self._next_check:          # 노드 한도는 정확히, 시간·정지는 일정 간격으로
            self._check_limits()
        pv = self.pv_table if beta - alpha > 1 else None
        if self.pv_table is not None:
            self.pv_table[ply] = ()
        if in_check is None:
            in_check = b.is_attacked(b.king_sq[b.side], b.side ^ 1)
        if check_rules and ply > 0:                   # negamax와 같은 규칙 처리 (직접 호출될 때만)
            kind = self._rule_kind(b)
            if kind is not None:
                self.draw_hits += 1
                if b.halfmove >= 100 and in_check and not b.has_legal_move(in_check=True):
                    return -MATE + ply
                if kind == AUTO:
                    return 0
                if beta <= 0:
                    return 0
                return max(0, self.quiesce(b, max(alpha, 0), beta, ply, in_check, check_rules=False,
                                           quiet_checks_left=quiet_checks_left))
        if ply >= MAX_PLY:
            return self._score_at_ply_limit(b, ply, in_check)

        if in_check:
            return self._quiesce_evasions(b, alpha, beta, ply, quiet_checks_left)

        cache = self._eval_cache
        if cache is None:
            stand_pat = evaluate(b)
        else:
            stand_pat = cache.get(b.hash)
            if stand_pat is None:
                stand_pat = evaluate(b)
                if len(cache) < self._eval_cache_limit:
                    cache[b.hash] = stand_pat
        # At the horizon a reversible quiet move can still be announced
        # to claim a draw. It need not be a check or capture. The normal
        # search already handles repeats inside the tree; probe announced
        # repetitions here only where the root game history can provide both
        # prior occurrences without a repeat along the searched path.
        if (stand_pat < 0 and (b.halfmove >= 99 or
                (b.halfmove >= 7 and len(b.history) - self.root_len <= 1))
                and self._can_announce_draw(b)):
            self.draw_hits += 1
            stand_pat = 0
        if stand_pat >= beta:
            # 컷하기 전에 스테일메이트가 아닌지 확인. has_legal_move의 빠른 길 덕분에
            # 대부분 기물 하나만 보고 끝나므로 비용이 작음.
            return stand_pat if b.has_legal_move(in_check=False) else 0
        best = stand_pat
        if stand_pat > alpha:
            alpha = stand_pat

        board = b.board
        # 잡는 수 + 앙파상 + 승격 4종(퀸·룩·비숍·나이트, 잡으며 승격 포함) 모두.
        # v0.3.2까지는 퀸 승격만 남겨서 나이트 승격 메이트, 퀸 승격이 스테일메이트인 국면 등을 놓쳤음.
        # 수 생성기(captures_only=True)가 이미 4종을 한 번씩만 만들므로 걸러내지만 않으면 됨.
        moves = b.pseudo_legal_moves(captures_only=True)
        # 정렬은 순서만 정함 (후보를 지우지 않음): 비싼 기물을 싼 기물로 잡는 수 먼저,
        # 승격은 새 기물 가치만큼 앞으로 (퀸 > 룩 > 비숍 > 나이트)
        moves.sort(key=lambda m: 10 * ORDER_VALUE[board[m.to]] - ORDER_VALUE[board[m.frm]]
                   + (ORDER_VALUE[m.promo] if m.promo else 0), reverse=True)
        searched_legal = False
        after_capture = int(self.qsearch_capture_bridge and quiet_checks_left == 2)
        qsel = self.selective and self.sel_qsearch and abs(alpha) < MATE_BOUND
        trace = self.selective_trace
        for m in moves:
            cutoff = None
            if qsel and not m.promo and m.to != b.ep:
                gain = ORDER_VALUE[board[m.to]]
                if stand_pat + gain + QS_DELTA <= alpha:
                    cutoff = 'qs_delta'
                elif ORDER_VALUE[board[m.frm]] > gain and b.see_estimate(m) < 0:
                    cutoff = 'qs_see'
                if cutoff:
                    king = b.king_sq[b.side ^ 1]
                    if max(abs(file_of(m.to) - file_of(king)), abs(rank_of(m.to) - rank_of(king))) <= 1:
                        cutoff = None
            # [실험용, 기본 꺼짐] 근사 델타 가지치기: "공짜로 잡아도 alpha에 못 미칠 것 같으면 생략".
            # stand_pat + gain + 200 은 실제 결과의 상한이 아님 (잡으면서 체크→메이트 등) → 메이트를 놓침.
            # 끈 상태에서는 잡은 뒤의 정적 탐색이 자기 stand pat으로 즉시 컷하므로(평가 1회),
            # 가망 없는 잡기도 '정확한 평가값'으로 걸러짐.
            if self.delta_pruning:
                gain = ORDER_VALUE[board[m.to]] + (ORDER_VALUE[m.promo] - 100 if m.promo else 0)
                if stand_pat + gain + 200 < alpha:
                    continue
            b.make_move(m)
            if b.is_attacked(b.king_sq[b.side ^ 1], b.side):
                b.unmake_move()
                continue
            searched_legal = True
            in_child_check = None
            if cutoff:
                in_child_check = b.in_check()
                if not in_child_check:
                    b.unmake_move()
                    if cutoff != 'qs_see' or b.see(m) < 0:
                        self.sel_stats[cutoff] += 1
                        if trace:
                            self._emit_trace(trace, cutoff, b, ply, 0, m, alpha, beta, stand_pat)
                        continue
                    b.make_move(m)
                self.sel_stats['qs_saved'] += 1
            # 잡기·승격은 halfmove를 0으로 만들므로 반복·50수 규칙에 걸릴 수 없음 → 규칙 확인 생략
            try:
                score = -self.quiesce(b, -beta, -alpha, ply + 1, in_check=in_child_check, check_rules=False,
                                      quiet_checks_left=after_capture)
            finally:
                b.unmake_move()
            if score > best:
                best = score
                if score > alpha:
                    if pv is not None:
                        pv[ply] = (m,) + pv[ply + 1]
                    alpha = score
                    if alpha >= beta:
                        break

        # v0.4.4: 체크 가능성 사전 필터로 후보를 줄이고, 실제로 수를 둔 뒤
        # 합법 체크 여부를 최종 판정한다. 직접·발견·캐슬링 체크 모두 포괄한다.
        # v0.4.3: 한정된 조용한 체크(비캡처·비승격 체크)를 정적 탐색에 추가한다.
        # 초반 qsearch 한 층에서만 검색하므로 조용한 체크의 무한 연쇄가 생기지 않는다.
        # 반드시 수를 둔 뒤 '합법 수' 및 '실제로 체크인지'를 판정한다(디스커버드 체크 포함).
        if quiet_checks_left > 0 and alpha < beta and ply + 1 < MAX_PLY:
            if self.check_continuation and quiet_checks_left == 1:
                self.check_continuation_nodes += 1
            for m in self._quiet_check_candidates(b):
                b.make_move(m)
                try:
                    if b.is_attacked(b.king_sq[b.side ^ 1], b.side):
                        continue                             # 핀 또는 불법 킹 이동
                    if not b.in_check():
                        continue                             # 체크가 아닌 조용한 수 제외
                    searched_legal = True
                    if self.qsearch_forcing_replies and self._too_many_evasions(b):
                        continue
                    child_rule = self._rule_child_score(b, ply)  # 조용한 체크는 50수/반복 가능
                    if child_rule is None:
                        score = -self.quiesce(b, -beta, -alpha, ply + 1,
                                              in_check=True, check_rules=False,
                                              quiet_checks_left=quiet_checks_left - 1)
                    else:
                        score = child_rule
                finally:
                    b.unmake_move()                           # 중단 예외 시에도 상태 복구
                if score > best:
                    best = score
                    if score > alpha:
                        if pv is not None:
                            pv[ply] = (m,) + (pv[ply + 1] if child_rule is None else ())
                        alpha = score
                        if alpha >= beta:
                            break

        # 합법적인 전술 수를 하나도 두지 못했다면 스테일메이트일 수 있으니 확인
        if not searched_legal and not b.has_legal_move(in_check=False):
            return 0
        return best

    @staticmethod
    def _can_announce_draw(board):
        # At least two occurrences of the *next* position must already
        # exist. Preselect by the opponent's side to move before generating.
        fifty = board.halfmove >= 99
        repeated = set()
        if not fifty and board.halfmove >= 7:
            seen = set()
            stop = max(0, len(board.history) - board.halfmove)
            for index in range(len(board.history)-1, stop-1, -2):
                key = board.history[index][H_HASH]
                if key in seen:
                    repeated.add(key)
                seen.add(key)
        if not fifty and not repeated:
            return False
        for move in board.pseudo_legal_moves():
            if board.board[move.frm] in 'Pp' or board.board[move.to] != EMPTY:
                continue
            board.make_move(move)
            try:
                if ((fifty or board.hash in repeated)
                        and not board.in_check(board.side ^ 1)):
                    return True
            finally:
                board.unmake_move()
        return False

    def _too_many_evasions(self, board):
        """Limit optional quiet checks; never filter evasions inside search."""
        remaining = self.qsearch_forcing_replies
        for move in board.evasion_candidates():
            board.make_move(move)
            legal = not board.in_check(board.side ^ 1)
            board.unmake_move()
            if legal:
                remaining -= 1
                if remaining < 0:
                    return True
        return False

    def _quiesce_evasions(self, b: Board, alpha, beta, ply, quiet_checks_left=0):
        """체크를 받은 국면: 평가값으로 멈출 수 없음 → 모든 합법 회피 수를 봄"""
        pv = self.pv_table if beta - alpha > 1 else None
        board = b.board
        moves = b.evasion_candidates() if self.fast_evasions else b.pseudo_legal_moves()
        moves.sort(key=lambda m: 10 * ORDER_VALUE[board[m.to]] - ORDER_VALUE[board[m.frm]]
                   if board[m.to] != EMPTY else -10_000, reverse=True)
        best = -INF
        legal = 0
        for m in moves:
            b.make_move(m)
            if b.is_attacked(b.king_sq[b.side ^ 1], b.side):
                b.unmake_move()
                continue
            legal += 1
            score = self._rule_child_score(b, ply) if b.halfmove >= 4 else None
            from_search = score is None
            try:
                if from_search:
                    score = -self.quiesce(b, -beta, -alpha, ply + 1, check_rules=False,
                                          quiet_checks_left=(quiet_checks_left if self.check_continuation else 0))
            finally:
                b.unmake_move()
            if score > best:
                best = score
                if score > alpha:
                    if pv is not None:
                        pv[ply] = (m,) + (pv[ply + 1] if from_search else ())
                    alpha = score
                    if alpha >= beta:
                        break
        if legal == 0:
            return -MATE + ply                         # 체크메이트 (negamax와 같은 거리 기준)
        return best

    @staticmethod
    def _score_at_ply_limit(board, ply, in_check):
        if board.has_legal_move(in_check=in_check):
            return evaluate(board)
        return -MATE + ply if in_check else 0

    # ──────────────────────────── 무승부 판정 (v0.3.2) ────────────────────────────
    def _rule_kind(self, b: Board):
        """국면 b에 걸리는 무승부 규칙: AUTO(0점으로 끝) / CLAIM(둘 차례인 쪽이 청구 가능) / None.
        해시 비교와 정수 비교뿐이라 빠름. 메이트 우선 처리는 부르는 쪽에서 함."""
        hm = b.halfmove
        if hm < 4:                      # 마지막 폰 이동·잡기 후 4수 미만이면 반복도 50수도 불가능
            return None
        rep = self._repetition_kind(b)
        if rep == 'tree' or rep == 'auto' or hm >= 150:
            return AUTO                 # 탐색용 반복 근사 / 5회 반복 / 75수 규칙
        if rep == 'claim' or hm >= 100:
            return CLAIM                # 3회 반복 / 50수 규칙
        return None

    def _rule_child_score(self, b: Board, ply):
        """ply에서 수를 둔 직후의 국면 b가 무승부 규칙에 걸리면 '수를 둔 쪽' 기준 점수, 아니면 None.

        AUTO  → 0점 (단 그 수가 메이트면 메이트가 우선)
        CLAIM → 수를 둔 쪽은 '이 수를 두면서' 청구할 수 있고(FIDE 9.2.1.1, 9.3.1),
                상대도 자기 차례에 청구할 수 있으므로(9.2.1.2, 9.3.2) 이 수의 가치는 정확히 0점.
                (둔 쪽이 이기고 있으면 상대가, 지고 있으면 둔 쪽이 청구함) 단 메이트면 메이트.
        어느 쪽이든 그 아래를 탐색할 필요가 없어 노드도 절약됨."""
        kind = self._rule_kind(b)
        if kind is None:
            return None
        self.draw_hits += 1             # 점수가 대국 이력에 의존 → 조상 노드는 TT에 점수 저장 안 함
        if b.halfmove >= 100 and b.in_check() and not b.has_legal_move(in_check=True):
            return MATE - (ply + 1)     # 50·75번째 수가 메이트 → 메이트가 우선
        return 0                        # 반복으로 생긴 국면은 메이트일 수 없음 (이전에 같은 국면에서 대국이 계속됐으므로)

    def _repetition_kind(self, b: Board):
        """지금 국면의 반복 상태
          'tree'  : 탐색 트리 안에서 이미 나왔던 국면 (탐색용 근사로 무승부 처리)
          'auto'  : 실제 대국 기록까지 합쳐 5번째 → 자동 무승부
          'claim' : 3·4번째 → 둘 차례인 쪽이 청구 가능
          None    : 그 외"""
        hist = b.history
        n = len(hist)
        stop = max(0, n - b.halfmove)
        h = b.hash
        count = 1
        for k in range(n - 2, stop - 1, -2):
            if hist[k][H_HASH] == h:
                if k >= self.root_len:
                    return 'tree'
                count += 1
        if count >= 5:
            return 'auto'
        if count >= 3:
            return 'claim'
        return None

    def _is_repetition_draw(self, b: Board):
        """(v0.3.1 호환용) 반복 때문에 무승부가 되거나 청구할 수 있는 국면인가"""
        return self._repetition_kind(b) is not None

    # ──────────────────────────── 보조 ────────────────────────────
    def order_moves(self, b: Board, moves, tt_move, ply, priority_checks=None):
        board = b.board
        killer1, killer2 = self.killers[ply]
        history = self.history
        ep = b.ep
        # A deliberately small, geometry-based ordering signal. It cannot change
        # correctness: no move is dropped and true search scores are untouched.
        if priority_checks is not None:
            king = b.king_sq[b.side ^ 1]
            kf, kr = file_of(king), rank_of(king)

        see_order = self.selective and self.sel_order

        def priority(m):
            if m == tt_move:
                return 10_000_000
            victim = board[m.to]
            if victim != EMPTY:                        # MVV-LVA: 비싼 걸 싼 걸로 잡는 수부터
                # [선택적 탐색] 그 칸에서 기물을 잃는 캡처는 킬러 뒤로 보낸다. 순서만 바뀌고
                # 깊이는 줄이지 않는다 (희생 수는 여전히 전부, 원래 깊이로 탐색).
                if (see_order and not m.promo and ORDER_VALUE[board[m.frm]] > ORDER_VALUE[victim]
                        and b.see_estimate(m) < 0):
                    return 750_000 + 10 * ORDER_VALUE[victim] - ORDER_VALUE[board[m.frm]]
                # 잡으며 승격하는 4종은 새 기물 가치로 순서만 나눔 (v0.3.3, 모두 탐색 대상)
                return (1_000_000 + 10 * ORDER_VALUE[victim] - ORDER_VALUE[board[m.frm]]
                        + (ORDER_VALUE[m.promo] if m.promo else 0))
            if m.promo:                                # 승격: 퀸 > 룩 > 비숍 > 나이트 순서로 (모두 탐색)
                return 950_000 + ORDER_VALUE[m.promo]
            if m.to == ep and board[m.frm] in 'Pp':
                return 1_000_900
            if priority_checks is not None and m in priority_checks:
                # Fast filter is intentionally overinclusive; checks are verified
                # by the normal legality/search logic, never assumed as facts.
                return 920_000
            if m == killer1:
                return 900_000
            if m == killer2:
                return 800_000
            score = history.get((board[m.frm], m.to), 0)
            if score > 700_000:
                score = 700_000
            if priority_checks is not None and board[m.frm].upper() in 'NBRQ':
                # Prefer developing a *piece* toward the enemy king among otherwise
                # quiet alternatives; this is only a sorting tie-break, not eval.
                ff, fr = file_of(m.frm), rank_of(m.frm)
                tf, tr = file_of(m.to), rank_of(m.to)
                before = max(abs(ff - kf), abs(fr - kr))
                after = max(abs(tf - kf), abs(tr - kr))
                if after < before:
                    score += (before - after) * 12_000
            return score

        moves.sort(key=priority, reverse=True)
        return moves

    def _check_limits(self):
        """노드 한도·정지 요청·시간 초과면 TimeUp. 다음 확인 시점도 여기서 정함:
        평소에는 CHECK_INTERVAL 노드 뒤, 노드 한도가 그보다 가까우면 한도 지점."""
        if self.node_limit and self.nodes >= self.node_limit:
            raise TimeUp
        if (self.stop_requested or (self.cancel_check and self.cancel_check())
                or (self.deadline and time.monotonic() >= self.deadline)):
            raise TimeUp
        nxt = self.nodes + self._check_interval()
        if self.node_limit:
            nxt = min(nxt, self.node_limit)
        self._next_check = nxt

    def _check_interval(self):
        if self.deadline is None:
            return CHECK_INTERVAL
        remaining = self.deadline - time.monotonic()
        if remaining <= 0.05:
            return 64
        if remaining <= 0.25:
            return 256
        return CHECK_INTERVAL


# ════════════════════════ 교육용: 미니맥스 vs 알파베타 비교 ════════════════════════
# 위의 Searcher에서 TT·정적탐색 등을 모두 뺀 '맨몸' 버전. 같은 깊이에서 같은 답을 내는지,
# 노드를 얼마나 아끼는지 비교해 봅니다.

def plain_minimax(b, depth, counter):
    if depth == 0:
        counter[0] += 1
        return evaluate(b)
    moves = b.legal_moves()
    if not moves:
        return -MATE if b.in_check() else 0
    best = -INF
    for m in moves:
        b.make_move(m)
        best = max(best, -plain_minimax(b, depth - 1, counter))
        b.unmake_move()
    return best


def plain_alphabeta(b, depth, alpha, beta, counter, ordered):
    if depth == 0:
        counter[0] += 1
        return evaluate(b)
    moves = b.legal_moves()
    if not moves:
        return -MATE if b.in_check() else 0
    if ordered:
        board = b.board
        moves.sort(key=lambda m: 10 * ORDER_VALUE[board[m.to]] - ORDER_VALUE[board[m.frm]]
                   if board[m.to] != EMPTY else -10_000, reverse=True)
    for m in moves:
        b.make_move(m)
        score = -plain_alphabeta(b, depth - 1, -beta, -alpha, counter, ordered)
        b.unmake_move()
        if score >= beta:
            return score
        alpha = max(alpha, score)
    return alpha


def compare_pruning(fen, depth):
    b = Board(fen)
    print(f"깊이 {depth}, 국면의 합법수 {len(b.legal_moves())}개")
    for name, fn in (("미니맥스 (가지치기 없음)", lambda c: plain_minimax(b, depth, c)),
                     ("알파베타 (정렬 없음)", lambda c: plain_alphabeta(b, depth, -INF, INF, c, False)),
                     ("알파베타 + 잡는 수 먼저", lambda c: plain_alphabeta(b, depth, -INF, INF, c, True))):
        counter = [0]
        t0 = time.monotonic()
        score = fn(counter)
        print(f"  {name:<22} 점수 {score:>+5}   평가한 국면 {counter[0]:>8,}개   {time.monotonic() - t0:5.1f}s")


if __name__ == '__main__':
    print("━━ 1. 미니맥스 vs 알파베타: 같은 답, 다른 노드 수 ━━")
    compare_pruning('r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4', 3)

    print("\n━━ 2. 2단계의 함정 국면: 퀸으로 폰을 잡을까? ━━")
    trap = Board('rnbqkbnr/pp3ppp/2p5/3p4/8/8/PPP2PPP/RNBQKBNR w KQkq - 0 4')
    print(trap)
    move, score = Searcher().search(trap, max_depth=4)
    print(f"→ 엔진의 선택: {move.uci()}  ({format_score(score)})")

    print("\n━━ 3. 메이트 찾기: 백 차례, 2수 메이트 ━━")
    mate2 = Board('3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1')
    print(mate2)
    move, score = Searcher().search(mate2, max_depth=6)
    print(f"→ 엔진의 선택: {move.uci()}  ({format_score(score)})")

    print("\n━━ 4. 스테일메이트 함정: Nxa1로 비숍을 잡으면 흑은 둘 수가 없음 ━━")
    stale = Board('7k/5K1p/7P/8/8/1N6/2PP4/b7 w - - 0 1')
    print(stale)
    move, score = Searcher().search(stale, max_depth=1)
    print(f"→ 깊이 1에서 엔진의 선택: {move.uci()}  ({format_score(score)})")

    print("\n━━ 5. 시작 국면에서 5초 생각하기 ━━")
    move, score = Searcher().search(Board(START_FEN), time_limit=5)
    print(f"→ 엔진의 선택: {move.uci()}  ({format_score(score)})")
