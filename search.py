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
from typing import NamedTuple, List

from board import (Board, Move, EMPTY, START_FEN, H_HASH, OFF, WHITE,
                   KNIGHT_STEPS, BISHOP_DIRS, ROOK_DIRS, QUEEN_DIRS,
                   file_of, rank_of)
from evaluate import evaluate

INF = 1_000_000
MATE = 100_000
MATE_BOUND = MATE - 1_000      # 이보다 절댓값이 크면 '메이트 점수'
MAX_PLY = 100

ENGINE_VERSION = "0.5.3"

EXACT, LOWER, UPPER, MOVE_ONLY = 0, 1, 2, 3   # TT 종류: 정확한 값 / 이 이상 / 이 이하 / 점수 없음
TT_HALFMOVE_MARGIN = 10        # 체크 연장 등으로 실제 수순이 깊이보다 길어질 수 있는 여유분

AUTO, CLAIM = 'auto', 'claim'  # 무승부 규칙 종류: 0점으로 끝 / 둘 차례인 쪽이 청구 가능

# 시간·정지 신호는 이 노드 수마다 확인 (time.time() 호출을 줄이려고). 노드 한도는 v0.4.1부터
# 이 간격과 무관하게 정확히 지킴: 다음 확인 시점을 '한도'보다 늦지 않게 잡음.
CHECK_INTERVAL = 1024

# 수 정렬용 기물 가치 (킹으로 잡는 수는 가장 마지막에)
ORDER_VALUE = {'.': 0}
for _p, _v in zip('PNBRQK', (100, 320, 330, 500, 900, 1000)):
    ORDER_VALUE[_p] = ORDER_VALUE[_p.lower()] = _v


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
            slots[i] = new
            return
        b = slots[i + 1]
        if b is not None and b[4] == key:
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
        self.check_continuation_nodes = 0
        # Conservative experimental late-move reductions (non-PV, quiet, non-checking
        # alternatives only). All tactical moves still receive full depth.
        self.lmr = False
        self.lmr_probes = 0
        self.lmr_researches = 0

    @property
    def tt_size(self):
        """TT 용량(항목 수). 바꾸면 TT를 그 크기로 새로 만듦 (내용은 비워짐)."""
        return self.tt.capacity

    @tt_size.setter
    def tt_size(self, capacity):
        self.tt.resize(capacity)

    # ──────────────────────────── 바깥에서 부르는 함수 ────────────────────────────
    def search(self, board: Board, max_depth=MAX_PLY, time_limit=None, node_limit=None,
               on_info=print_info, root_moves=None):
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
        멈추면 마지막으로 끝낸 깊이의 최선수, 깊이 1도 못 끝냈으면 그때까지의 최선 또는 첫 합법수.
        탐색이 시간 초과·정지·예외로 끊겨도 board는 호출 전 상태 그대로 돌아옵니다."""
        self.nodes = 0
        self.start = time.time()
        self.deadline = self.start + time_limit if time_limit else None
        self.node_limit = node_limit
        self._next_check = min(CHECK_INTERVAL, node_limit) if node_limit else CHECK_INTERVAL
        self.stop_requested = False
        self.root_filter = None
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
        self.root_len = len(board.history)
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

            best_move, best_score = None, 0
            for depth in range(1, max_depth + 1):
                self.root_best = None
                try:
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
                elapsed = time.time() - self.start
                if on_info:
                    on_info(SearchInfo(depth, score, self.nodes, elapsed,
                                       self.principal_variation(board, best_move, depth)))
                plies = mate_plies(score)
                if plies is not None and plies <= depth:
                    break  # 이 깊이 안에서 메이트가 확정 → 더 볼 필요 없음
                if self.deadline and elapsed > (self.deadline - self.start) * 0.5:
                    break  # 남은 시간으로는 다음 깊이를 끝내기 어려움
            if best_move is None:
                best_move = candidates[0]           # 깊이 1도 못 끝냄 → 합법적인 대체 수
            return best_move, best_score
        finally:
            board.restore(state)                    # 어떤 예외가 나도 국면은 원래대로
            self.root_filter = None

    # ──────────────────────────── 탐색 본체 ────────────────────────────
    def negamax(self, b: Board, depth, alpha, beta, ply, check_rules=True):
        self.nodes += 1
        if self.nodes >= self._next_check:          # 노드 한도는 정확히, 시간·정지는 일정 간격으로
            self._check_limits()
        root = ply == 0
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
                return max(0, self.negamax(b, depth, max(alpha, 0), beta, ply, check_rules=False))

        if in_check:
            depth += 1                                 # 체크 연장
        if depth <= 0:
            return self.quiesce(b, alpha, beta, ply, in_check=False, check_rules=False)
        if ply >= MAX_PLY:
            return evaluate(b)

        # ── 트랜스포지션 테이블 조회 ──
        alpha_orig = alpha
        tt_move = None
        entry = self.tt.get(b.hash)
        if entry is not None:
            e_depth, e_flag, e_score, tt_move = entry[0], entry[1], entry[2], entry[3]
            if (not root and e_flag != MOVE_ONLY and e_depth >= depth
                    and b.halfmove + e_depth + TT_HALFMOVE_MARGIN < 100):
                s = _from_tt(e_score, ply)             # 충분히 깊게 본 결과면 그대로 사용
                if e_flag == EXACT:
                    return s
                if e_flag == LOWER and s >= beta:
                    return s
                if e_flag == UPPER and s <= alpha:
                    return s

        # ── 모든 수 시도 ──
        best_score, best_move = -INF, None
        legal = 0
        board = b.board
        moves = b.pseudo_legal_moves()
        if root and self.root_filter is not None:      # go searchmoves: 루트 후보만 남김 (아래 깊이는 전부)
            moves = [m for m in moves if m in self.root_filter]
        # Tactical ordering is limited to the upper tree and low remaining depths:
        # do not pay the geometric/check-candidate overhead at every leaf.
        priority_checks = None
        if self.tactical_ordering and ply <= 2 and not in_check and depth <= 4:
            priority_checks = set(self._quiet_check_candidates(b, moves=moves))
            self.tactical_order_nodes += 1
            self.tactical_order_candidates += len(priority_checks)
        for m in self.order_moves(b, moves, tt_move, ply, priority_checks):
            piece = board[m.frm]
            quiet = board[m.to] == EMPTY and not m.promo and not (
                m.to == b.ep and piece in 'Pp')
            b.make_move(m)
            if b.is_attacked(b.king_sq[b.side ^ 1], b.side):   # 내 킹이 체크에 남는 수 = 불법
                b.unmake_move()
                continue
            legal += 1
            score = self._rule_child_score(b, ply)    # 둔 결과가 무승부 규칙에 걸리면 바로 점수
            if score is None:
                # LMR reduces ONLY late quiet moves at non-PV nodes. Never reduce
                # captures, promotions, pawn pushes to the seventh, replies to check,
                # moves giving check, TT moves or killers. On a reduced fail-high,
                # always re-search at full depth. This is SELECTIVE: unlike PVS it
                # need not preserve full-width scores, so it is an opt-in experiment.
                quiet_noncheck = (quiet and not b.in_check()) if self.lmr else False
                pawn_near_promotion = (piece in 'Pp' and
                    (rank_of(m.to) >= 6 if piece == 'P' else rank_of(m.to) <= 1))
                do_lmr = (self.lmr and not root and not in_check and
                    depth >= 3 and legal >= 4 and beta - alpha == 1 and
                    quiet_noncheck and not pawn_near_promotion and
                    m != tt_move and m not in self.killers[ply] and
                    self.history.get((piece, m.to), 0) < depth * depth * 4)
                if do_lmr:
                    self.lmr_probes += 1
                    score = -self.negamax(b, depth - 2, -alpha - 1, -alpha,
                                          ply + 1, check_rules=False)
                    if score > alpha:
                        self.lmr_researches += 1
                        score = -self.negamax(b, depth - 1, -beta, -alpha,
                                              ply + 1, check_rules=False)
                elif self.pvs and legal > 1 and beta - alpha > 1:
                    # PVS: 첫 합법 수는 이미 전체 창에서 확인했다. 이후 수의 경우
                    # 기존 alpha를 넘을 수 있는지만 먼저 1cp 창으로 검사한다.
                    # null-window 값은 fail-soft 경계일 수 있으므로 alpha < score < beta면
                    # 전체 창으로 재탐색해야 정확한 점수와 PV를 구할 수 있다.
                    self.pvs_probes += 1
                    score = -self.negamax(b, depth - 1, -alpha - 1, -alpha,
                                          ply + 1, check_rules=False)
                    if alpha < score < beta:
                        self.pvs_researches += 1
                        score = -self.negamax(b, depth - 1, -beta, -alpha,
                                              ply + 1, check_rules=False)
                else:
                    score = -self.negamax(b, depth - 1, -beta, -alpha,
                                          ply + 1, check_rules=False)
            b.unmake_move()

            if score > best_score:
                best_score, best_move = score, m
                if root:
                    self.root_best = m
                if score > alpha:
                    alpha = score
                    if alpha >= beta:                  # 베타 컷: 상대가 이 국면을 허용하지 않음
                        if quiet:                      # 조용한 수가 컷을 냈다면 기억해 둠
                            k = self.killers[ply]
                            if k[0] != m:
                                k[0], k[1] = m, k[0]
                            key = (piece, m.to)
                            self.history[key] = self.history.get(key, 0) + depth * depth
                        break

        if legal == 0:                                 # 둘 수가 없음
            return -MATE + ply if in_check else 0      # 체크메이트(거리 반영) / 스테일메이트

        if root and self.root_filter is not None:
            pass        # 후보를 제한한 루트 점수는 '이 국면의 값'이 아님 → TT에 저장하지 않음
        elif self.draw_hits == draw_hits_before:       # 이력과 무관한 결과만 점수까지 저장
            flag = UPPER if best_score <= alpha_orig else LOWER if best_score >= beta else EXACT
            self.tt.store(b.hash, depth, flag, _to_tt(best_score, ply), best_move)
        elif entry is None:
            self.tt.store(b.hash, 0, MOVE_ONLY, 0, best_move)
        return best_score

    def _quiet_check_candidates(self, b: Board, moves=None):
        """모든 조용한 체크를 포함하는 *과포함* 후보 필터.

        탐색 후보를 실제로 두기 전의 가벼운 판정만 사용한다. 직접 체크(폰/나이트/슬라이더),
        디스커버드 체크, 캐슬링 룩 체크를 포괄한다. False positive는 뒤의 정확한 검사에서
        제거한다. False negative는 전술 누락이므로 독립 기준과 비교 테스트한다.
        """
        if moves is None:
            moves = b.pseudo_legal_moves()
        if not self.qsearch_fast_checks:
            # v0.4.3 baseline: every quiet move is made/unmade to test check.
            for m in moves:
                p = b.board[m.frm]
                if b.board[m.to] == EMPTY and not m.promo and not (m.to == b.ep and p in 'Pp'):
                    yield m
            return
        board = b.board
        target = b.king_sq[b.side ^ 1]
        own = 'PNBRQK' if b.side == WHITE else 'pnbrqk'
        # 상대 킹 방향으로 두 번째 자신의 슬라이더가 있고, 그 사이 첫 기물이 내 기물이라면
        # 첫 기물이 움직이며 발견 체크를 낼 수 있다. 이동 방향에 따라 막힌 채일 수도 있음.
        discovered = set()
        for direction in QUEEN_DIRS:
            s = target + direction
            while board[s] == EMPTY:
                s += direction
            first = s
            if board[first] not in own:
                continue
            s += direction
            while board[s] == EMPTY:
                s += direction
            slider = board[s].upper()
            if slider == 'Q' or (direction in ROOK_DIRS and slider == 'R') or (direction in BISHOP_DIRS and slider == 'B'):
                if board[s] in own:
                    discovered.add(first)

        tf, tr = file_of(target), rank_of(target)
        for m in moves:
            moving = board[m.frm]
            if board[m.to] != EMPTY or m.promo or (m.to == b.ep and moving in 'Pp'):
                continue
            kind = moving.upper()
            if m.frm in discovered:
                yield m
                continue
            if kind == 'K':
                # 캐슬링은 룩의 위치도 바뀌므로 직접 체크 가능성을 배제하지 않는다.
                if abs(m.to - m.frm) == 2:
                    yield m
                continue
            delta = target - m.to
            if kind == 'N':
                if delta in KNIGHT_STEPS:
                    yield m
                continue
            if kind == 'P':
                if delta in ((9, 11) if b.side == WHITE else (-9, -11)):
                    yield m
                continue
            # 비숍·룩·퀸은 도착 칸에서 상대 킹까지 막히지 않은 같은 선이어야 한다.
            df, dr = tf - file_of(m.to), tr - rank_of(m.to)
            if kind == 'B':
                if abs(df) != abs(dr):
                    continue
            elif kind == 'R':
                if df != 0 and dr != 0:
                    continue
            elif kind == 'Q':
                if not (df == 0 or dr == 0 or abs(df) == abs(dr)):
                    continue
            else:
                continue
            if df == 0:
                step = 10 if dr > 0 else -10
            elif dr == 0:
                step = 1 if df > 0 else -1
            else:
                step = (10 if dr > 0 else -10) + (1 if df > 0 else -1)
            scan = m.to + step
            while scan != target and (board[scan] == EMPTY or scan == m.frm):
                scan += step
            if scan == target:
                yield m

    def quiesce(self, b: Board, alpha, beta, ply, in_check=None, check_rules=True,
                quiet_checks_left=None):
        """정적 탐색. 체크가 아니면 잡는 수·앙파상·승격(4종 모두)만, 체크면 모든 회피 수를 봄.
        in_check를 이미 알고 있으면 넘겨서 중복 계산을 피함.
        check_rules: 무승부 규칙 확인 여부 (탐색 내부에서는 부모가 이미 확인해서 False).
        quiet_checks_left: 이번 qsearch 가지에서 허용할 조용한 체크 횟수.
          기본 TacticalChecks에서는 1개만 허용. CheckContinuation이 켜지면
          조용한 체크→강제 회피→두 번째 조용한 체크를 1회 추가로 허용.
          캡처 가지에서는 기존처럼 budget=0 (가지 폭발 제한).
        """
        if quiet_checks_left is None:
            quiet_checks_left = (2 if self.check_continuation else 1) if self.qsearch_quiet_checks else 0
        self.nodes += 1
        if self.nodes >= self._next_check:          # 노드 한도는 정확히, 시간·정지는 일정 간격으로
            self._check_limits()
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
            return evaluate(b)

        if in_check:
            return self._quiesce_evasions(b, alpha, beta, ply, quiet_checks_left)

        stand_pat = evaluate(b)        # "아무것도 안 잡고 멈춰도 이 정도는 된다"
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
        for m in moves:
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
            # 잡기·승격은 halfmove를 0으로 만들므로 반복·50수 규칙에 걸릴 수 없음 → 규칙 확인 생략
            try:
                score = -self.quiesce(b, -beta, -alpha, ply + 1, check_rules=False,
                                      quiet_checks_left=0)
            finally:
                b.unmake_move()
            if score > best:
                best = score
                if score > alpha:
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
                    child_rule = self._rule_child_score(b, ply)  # 조용한 체크는 50수/반복 가능
                    if child_rule is None:
                        score = -self.quiesce(b, -beta, -alpha, ply + 1,
                                              check_rules=False, quiet_checks_left=quiet_checks_left - 1)
                    else:
                        score = child_rule
                finally:
                    b.unmake_move()                           # 중단 예외 시에도 상태 복구
                if score > best:
                    best = score
                    if score > alpha:
                        alpha = score
                        if alpha >= beta:
                            break

        # 합법적인 전술 수를 하나도 두지 못했다면 스테일메이트일 수 있으니 확인
        if not searched_legal and not b.has_legal_move(in_check=False):
            return 0
        return best

    def _quiesce_evasions(self, b: Board, alpha, beta, ply, quiet_checks_left=0):
        """체크를 받은 국면: 평가값으로 멈출 수 없음 → 모든 합법 회피 수를 봄"""
        board = b.board
        moves = b.pseudo_legal_moves()
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
            score = self._rule_child_score(b, ply)    # 회피 수는 조용한 수일 수 있어 규칙 확인
            try:
                if score is None:
                    score = -self.quiesce(b, -beta, -alpha, ply + 1, check_rules=False,
                                          quiet_checks_left=(quiet_checks_left if self.check_continuation else 0))
            finally:
                b.unmake_move()
            if score > best:
                best = score
                if score > alpha:
                    alpha = score
                    if alpha >= beta:
                        break
        if legal == 0:
            return -MATE + ply                         # 체크메이트 (negamax와 같은 거리 기준)
        return best

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

        def priority(m):
            if m == tt_move:
                return 10_000_000
            victim = board[m.to]
            if victim != EMPTY:                        # MVV-LVA: 비싼 걸 싼 걸로 잡는 수부터
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
            score = min(history.get((board[m.frm], m.to), 0), 700_000)
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

    def principal_variation(self, b: Board, first: Move, max_len):
        """TT에 남은 최선수를 따라가며 예상 수순을 복원"""
        pv, seen = [first], {b.hash}
        b.make_move(first)
        while len(pv) < max_len:
            entry = self.tt.get(b.hash)
            if entry is None or entry[3] is None or b.hash in seen:
                break
            m = entry[3]
            if m not in b.legal_moves():
                break
            seen.add(b.hash)
            b.make_move(m)
            pv.append(m)
        for _ in pv:
            b.unmake_move()
        return pv

    def _check_limits(self):
        """노드 한도·정지 요청·시간 초과면 TimeUp. 다음 확인 시점도 여기서 정함:
        평소에는 CHECK_INTERVAL 노드 뒤, 노드 한도가 그보다 가까우면 한도 지점."""
        if self.node_limit and self.nodes >= self.node_limit:
            raise TimeUp
        if self.stop_requested or (self.deadline and time.time() >= self.deadline):
            raise TimeUp
        nxt = self.nodes + CHECK_INTERVAL
        if self.node_limit:
            nxt = min(nxt, self.node_limit)
        self._next_check = nxt


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
        t0 = time.time()
        score = fn(counter)
        print(f"  {name:<22} 점수 {score:>+5}   평가한 국면 {counter[0]:>8,}개   {time.time() - t0:5.1f}s")


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
