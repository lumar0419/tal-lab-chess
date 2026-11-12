"""
evaluate.py — 2단계: 평가함수

국면 하나를 보고 "누가 얼마나 유리한가"를 숫자 하나로 매깁니다.
단위는 센티폰(centipawn): 폰 1개 = 100. +150이면 "폰 1.5개만큼 유리".
엔진의 '실력'과 '성격'은 대부분 여기서 정해집니다.

이 엔진의 평가 항목
  1) 기물 가치      폰 100, 나이트 320, 비숍 330, 룩 500, 퀸 900
  2) 위치 점수표    같은 나이트라도 중앙에 있으면 +, 구석에 있으면 − (PST, piece-square table)
  3) 폰 구조        겹폰(−), 고립폰(−), 통과폰(+, 종반일수록 크게)
  4) 비숍 쌍        비숍 2개를 모두 가지고 있으면 +
  5) 킹 안전          폰 실드, 킹 주변의 열린 파일, 킹 주변을 노리는 상대 기물과 지키는 내 기물 (중반에만 반영)
                     v0.4.1 추가, v0.4.2 개정. KING_SAFETY로 켬/끔 (UCI 옵션 KingSafety). 기본값 끔 — 아래 5) 설명 참고

속도 (v0.4.2)
  탐색이 부르는 evaluate()는 '빠른 경로'(표 합치기 + 폰 캐시)를 쓰고, eval_terms()/explain()은 항목별로
  따로 계산하는 느린 기준 경로입니다. 두 경로의 값은 항상 같아야 하며 테스트가 확인합니다.

테이퍼드 평가 (tapered evaluation)
  중반과 종반은 좋은 수의 기준이 다릅니다. 중반엔 킹이 구석에 숨어야 안전하고,
  종반엔 킹이 중앙으로 나와 싸워야 합니다. 그래서 각 항목을 '중반 점수(mg)'와
  '종반 점수(eg)' 두 개로 매기고, 판에 남은 기물 양(phase)에 따라 섞습니다.
      phase = 나이트·비숍 1, 룩 2, 퀸 4 의 합 (시작 국면 = 24, 기물이 다 빠지면 0)
      최종 = (mg × phase + eg × (24 − phase)) / 24

점수 방향
  evaluate()는 '지금 둘 차례인 쪽' 기준 점수를 돌려줍니다 (3단계 negamax 탐색이 이 형태를 씀).
  사람이 볼 때는 evaluate_white()처럼 '백 기준'이 편합니다.

위치 점수표 값은 chessprogramming.org의 'Simplified Evaluation Function'을 바탕으로 했고,
폰 구조·비숍 쌍 수치는 이 프로젝트에서 정한 출발값입니다. 전부 마음대로 바꿔 보세요.
"""

from board import (Board, WHITE, BLACK, SQUARES, EMPTY, START_FEN, sq, rank_of,
                   KNIGHT_STEPS, BISHOP_DIRS, ROOK_DIRS, QUEEN_DIRS, KING_STEPS, OFF)

# ──────────────────────────── 1) 기물 가치 ────────────────────────────
PIECE_VALUE = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}

# ──────────────────────────── 2) 위치 점수표 ────────────────────────────
# 백 입장에서, 보이는 그대로 (첫 줄 = 8랭크, 마지막 줄 = 1랭크, 왼쪽 = a파일)
PAWN = [
     0,   0,   0,   0,   0,   0,   0,   0,
    50,  50,  50,  50,  50,  50,  50,  50,
    10,  10,  20,  30,  30,  20,  10,  10,
     5,   5,  10,  25,  25,  10,   5,   5,
     0,   0,   0,  20,  20,   0,   0,   0,
     5,  -5, -10,   0,   0, -10,  -5,   5,
     5,  10,  10, -20, -20,  10,  10,   5,
     0,   0,   0,   0,   0,   0,   0,   0,
]
KNIGHT = [
   -50, -40, -30, -30, -30, -30, -40, -50,
   -40, -20,   0,   0,   0,   0, -20, -40,
   -30,   0,  10,  15,  15,  10,   0, -30,
   -30,   5,  15,  20,  20,  15,   5, -30,
   -30,   0,  15,  20,  20,  15,   0, -30,
   -30,   5,  10,  15,  15,  10,   5, -30,
   -40, -20,   0,   5,   5,   0, -20, -40,
   -50, -40, -30, -30, -30, -30, -40, -50,
]
BISHOP = [
   -20, -10, -10, -10, -10, -10, -10, -20,
   -10,   0,   0,   0,   0,   0,   0, -10,
   -10,   0,   5,  10,  10,   5,   0, -10,
   -10,   5,   5,  10,  10,   5,   5, -10,
   -10,   0,  10,  10,  10,  10,   0, -10,
   -10,  10,  10,  10,  10,  10,  10, -10,
   -10,   5,   0,   0,   0,   0,   5, -10,
   -20, -10, -10, -10, -10, -10, -10, -20,
]
ROOK = [
     0,   0,   0,   0,   0,   0,   0,   0,
     5,  10,  10,  10,  10,  10,  10,   5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
    -5,   0,   0,   0,   0,   0,   0,  -5,
     0,   0,   0,   5,   5,   0,   0,   0,
]
QUEEN = [
   -20, -10, -10,  -5,  -5, -10, -10, -20,
   -10,   0,   0,   0,   0,   0,   0, -10,
   -10,   0,   5,   5,   5,   5,   0, -10,
    -5,   0,   5,   5,   5,   5,   0,  -5,
     0,   0,   5,   5,   5,   5,   0,  -5,
   -10,   5,   5,   5,   5,   5,   0, -10,
   -10,   0,   5,   0,   0,   0,   0, -10,
   -20, -10, -10,  -5,  -5, -10, -10, -20,
]
KING_MG = [  # 중반: 캐슬링한 구석이 안전, 중앙으로 나오면 벌점
   -30, -40, -40, -50, -50, -40, -40, -30,
   -30, -40, -40, -50, -50, -40, -40, -30,
   -30, -40, -40, -50, -50, -40, -40, -30,
   -30, -40, -40, -50, -50, -40, -40, -30,
   -20, -30, -30, -40, -40, -30, -30, -20,
   -10, -20, -20, -20, -20, -20, -20, -10,
    20,  20,   0,   0,   0,   0,  20,  20,
    20,  30,  10,   0,   0,  10,  30,  20,
]
KING_EG = [  # 종반: 킹도 싸우는 기물 → 중앙이 좋음
   -50, -40, -30, -20, -20, -30, -40, -50,
   -30, -20, -10,   0,   0, -10, -20, -30,
   -30, -10,  20,  30,  30,  20, -10, -30,
   -30, -10,  30,  40,  40,  30, -10, -30,
   -30, -10,  30,  40,  40,  30, -10, -30,
   -30, -10,  20,  30,  30,  20, -10, -30,
   -30, -30,   0,   0,   0,   0, -30, -30,
   -50, -30, -30, -30, -30, -30, -30, -50,
]
TABLES = {  # 기물: (중반 표, 종반 표)
    'P': (PAWN, PAWN), 'N': (KNIGHT, KNIGHT), 'B': (BISHOP, BISHOP),
    'R': (ROOK, ROOK), 'Q': (QUEEN, QUEEN), 'K': (KING_MG, KING_EG),
}

# ──────────────────────────── 3) 폰 구조 / 4) 비숍 쌍 ────────────────────────────
DOUBLED = (-10, -20)    # (중반, 종반) 같은 파일에 내 폰이 2개 이상 → 초과분마다
ISOLATED = (-10, -15)   # 양옆 파일에 내 폰이 하나도 없음
# 통과폰: 앞길(같은 파일 + 양옆 파일)에 상대 폰이 없음. 상대적 랭크(출발 랭크=1)별 보너스
PASSED_MG = (0, 5, 10, 15, 25, 40, 60, 0)
PASSED_EG = (0, 10, 15, 25, 45, 75, 120, 0)
BISHOP_PAIR = (30, 50)

PHASE_WEIGHT = {'N': 1, 'B': 1, 'R': 2, 'Q': 4}
MAX_PHASE = 24

# ──────────────────────────── 5) 킹 안전 (v0.4.1 추가, v0.4.2 개정) ────────────────────────────
# 모두 '중반 점수'에만 들어감 → 테이퍼드 평가로 기물이 빠질수록 자연히 0에 가까워지고,
# 종반에는 기존 KING_EG 표(킹이 중앙으로 나오면 +)가 그대로 킹 활동을 장려함.
#
# v0.4.2에서 바뀐 점 (v0.4.1은 '상대 퀸이 있을 때만' 전부 계산했음)
#   · 퀸 유무 대신 '상대 공격력'(상대 나이트·비숍·룩·퀸의 공격 단위 합, 시작 국면 19)을 기준으로 함.
#       공격력 < KS_MIN_POWER(4)     기물이 하나 이하 → 아무것도 계산하지 않음 (종반 비용 절약)
#       공격력 < KS_STRUCT_POWER(6)  폰 구조(실드·열린 파일) 벌점 없음 (공격할 기물이 부족)
#       그 이상                       폰 구조 벌점 × min(공격력, 16)/16  — 퀸 없는 중반(최대 14)도 반영되지만 약하게
#   · 킹 공격은 퀸이 없어도 계산 (두 룩, 룩+비숍, 룩+나이트, 경량 기물 여럿). 실제로 킹 구역에 닿은
#     기물이 2개 이상일 때만이라, 공격이 없는 종반에서는 0.
#   · 수비 기물: 킹 구역을 지키는 내 나이트·비숍·룩·퀸 하나마다 공격 단위 1을 상쇄 (최대 공격 단위의 절반까지:
#       수비가 아무리 많아도 여러 기물의 공격이 0이 되지는 않음).
#       v0.4.1은 수비를 보지 않아, 잘 지켜진 캐슬링 킹도 퀸+비숍이 닿기만 하면 -73이었음.
#   · 열린 파일 벌점은 상대에게 룩이나 퀸이 있을 때만, 그 파일에 실제로 룩·퀸이 있으면 추가 벌점.
#
# KING_SAFETY: 켬/끔 (UCI 옵션 KingSafety). 끄면 v0.4.0 평가와 값이 같음.
#   기본값은 '끔'. 근거 (v0.4.2 실험, Stockfish 16 UCI_Elo 1700, 10초+0.1초, 순차·교차 실행, 설정마다 80판):
#     끔 41승 18무 21패 (62.5%) / 켬 30승 13무 37패 (45.6%), 같은 오프닝·색끼리 80짝의 차이 -16.9%
#     (95% 범위 -30.6% ~ -3.2%). v0.4.1 공식으로 한 이전 실험(40판씩)에서도 켠 쪽이 낮았음.
#   이 엔진은 대국에서 평균 깊이 3.6 정도만 보므로, 킹 주변 공격 점수가 탐색이 확인하지 못한 공격을
#   과대평가하게 만드는 것으로 보임 (가중치는 손으로 정한 값이고 튜닝하지 않았음).
#   탐색이 깊어지거나 가중치를 대국으로 맞춘 뒤 다시 실험할 수 있도록 코드와 옵션은 남겨 둠.
KING_SAFETY = False
KS_MIN_POWER = 4
KS_STRUCT_POWER = 6
KS_FULL_POWER = 16
# 폰 실드: 킹이 측면(a~c, f~h 파일)의 자기 진영 첫 두 랭크에 있을 때, 킹 파일과 양옆 파일에서
#   킹 바로 앞(1칸) 폰 = 0, 2칸 앞 폰 = SHIELD_ADVANCED, 2칸 안에 자기 폰 없음 = SHIELD_MISSING.
#   중앙(d·e 파일) 킹은 실드 대신 위치 점수표(KING_MG: 캐슬링 자리 +, 중앙 −)와 열린 파일 항목이 맡음
#   → 같은 사실을 두 번 세지 않으려는 것. 1.e4만으로 e1 킹에 실드 벌점이 붙는 일도 없음.
#   (KING_MG와의 관계: KING_MG는 '킹이 어느 칸에 있는가'만, 이 항목은 '그 앞의 폰이 어떤가'만 봄.)
SHIELD_ADVANCED = -10
SHIELD_MISSING = -20
# 킹 파일과 양옆 파일: 폰이 하나도 없음(열린 파일) / 내 폰만 없음(반쯤 열림). 상대에게 룩·퀸이 있을 때만.
#   그 파일에 상대 룩·퀸이 실제로 있으면 HEAVY_ON_FILE 추가.
OPEN_FILE = -15
HALF_OPEN_FILE = -8
HEAVY_ON_FILE = -10
# 킹 공격: '킹 구역'(킹 칸 + 주변 8칸) 중 한 칸이라도 공격하는 상대 기물(폰·킹 제외)을 공격자로 셈.
#   공격자가 2개 이상일 때만: 위험도 = 공격 단위 합 − min(수비 기물 수, 단위 합의 절반),
#   벌점 = 위험도² × 3/2 (최대 ATTACK_CAP).
#   제곱이라 공격자가 늘수록 빠르게 커짐. 수비 0일 때: N+B 24, R+N 37, R+R 54, Q+N 73, Q+R 96, Q+R+B 150.
#   수비 3(예: Rf1·Nf3·Qd1)이면: Q+B 24, Q+R 37, Q+R+B 73.
#   공격자 하나뿐이면 0: 혼자서는 킹을 잡기 어렵고, 체크·메이트 위협은 탐색(정적 탐색 포함)이 직접 봄.
#   '공격 가능 칸'(가로막는 기물까지 닿는 칸)을 셈. 핀이나 실제 합법 여부는 따지지 않음
#   (핀된 기물도 압박은 하고, 합법성 확인은 평가마다 하기엔 너무 비쌈).
#   검토했지만 넣지 않은 것: 구역 안 '공격받는 칸의 개수'(칸별 공격 지도가 필요해 비용이 큼),
#   체크 가능한 수 세기(합법수 생성이 필요).
ATTACK_UNITS = {'N': 2, 'B': 2, 'R': 3, 'Q': 5}
ATTACK_CAP = 250


# ──────────────────────────── 공격적 기물 활동성 (v0.4.4, 실험 옵션) ────────────────────────────
# 네 가지 기물(나이트·비숍·룩·퀸)의 폰에게 공격받지 않는 활동 칸을 가볍게 평가.
# 킹 구역에 기물 둘 이상이 압박을 가하면 작은 협력 보너스를 준다.
# 기물 희생 자체에는 점수를 주지 않는다. 합법수 개수나 확실한 주도권을 뜻하지 않으며,
# 핀·상대 장거리 기물 공격은 아직 고려하지 않은 근사값이다.
# 실제 Elo 및 Tal 스타일 일치도는 검증 전이므로 기본 OFF.
ATTACK_ACTIVITY = False
# v0.4.6: limited forcing-threat initiative heuristic. OFF until controlled games
# establish value. This is NOT a sacrifice reward or a proof of compensation.
INITIATIVE = False
INITIATIVE_CAP = 36  # cap in centipawns, before phase tapering
_ACTIVITY_BASE = {'N': 4, 'B': 5, 'R': 6, 'Q': 8}
_ACTIVITY_MG = {'N': 3, 'B': 2, 'R': 1, 'Q': 1}
_ACTIVITY_EG = {'N': 2, 'B': 2, 'R': 1, 'Q': 1}
_ACTIVITY_DIRECTIONS = {'N': KNIGHT_STEPS, 'B': BISHOP_DIRS,
                        'R': ROOK_DIRS, 'Q': QUEEN_DIRS}


# (색, 칸) → 그 폰이 공격하는 유효한 칸. 실행 중 반복 계산하지 않는다.
_ACTIVITY_PAWN_TARGETS = {
    WHITE: {s: tuple(t for t in (s + 9, s + 11) if 21 <= t <= 98 and 1 <= t % 10 <= 8)
            for s in SQUARES},
    BLACK: {s: tuple(t for t in (s - 9, s - 11) if 21 <= t <= 98 and 1 <= t % 10 <= 8)
            for s in SQUARES},
}
_ACTIVITY_INDEX_KIND = ('B', 'Q', 'R', 'N')  # _PIECE_AT의 타입 번호와 동일


def _attack_activity_parts(board, pieces, pawn_squares):
    """빠른 평가 루프에서 이미 모은 기물 정보와 폰 칸으로 공격 활동성을 평가."""
    b = board.board
    guarded = (set(), set())
    for c in (WHITE, BLACK):
        coverage = guarded[c]
        target_map = _ACTIVITY_PAWN_TARGETS[c]
        for s in pawn_squares[c]:
            coverage.update(target_map[s])
    results = [None, None]
    for c in (WHITE, BLACK):
        own = 'PNBRQK' if c == WHITE else 'pnbrqk'
        danger = guarded[c ^ 1]
        zone = _KING_ZONES[board.king_sq[c ^ 1]]
        mg = eg = attackers = 0
        for square, index, _ in pieces[c]:
            kind = _ACTIVITY_INDEX_KIND[index]
            safe = pressure = 0
            sliding = kind != 'N'
            for direction in _ACTIVITY_DIRECTIONS[kind]:
                t = square + direction
                while b[t] != OFF:
                    occupant = b[t]
                    if occupant in own:
                        break
                    if t not in danger:
                        safe += 1
                        pressure += (t in zone)
                    if not sliding or occupant != EMPTY:
                        break
                    t += direction
            difference = max(-4, min(8, safe - _ACTIVITY_BASE[kind]))
            mg += difference * _ACTIVITY_MG[kind]
            eg += difference * _ACTIVITY_EG[kind]
            if pressure:
                attackers += 1
                mg += 3 * min(pressure, 4)
        if attackers >= 2:
            mg += min((attackers - 1) * 5, 15)
        results[c] = mg, eg
    return results[WHITE][0] - results[BLACK][0], results[WHITE][1] - results[BLACK][1]


def attack_activity_terms(board):
    """기물의 '안전한 활동 칸 + 상대 킹 압박' (백 기준 mg/eg).

    독립적으로도 호출 가능. 핀·적 슬라이더의 공격을 생략한 근사값이며
    무작위 희생에 직접 점수를 주지는 않는다.
    """
    b = board.board
    pieces = ([], [])
    pawn_squares = ([], [])
    for s in SQUARES:
        p = b[s]
        if p == 'P':
            pawn_squares[WHITE].append(s)
        elif p == 'p':
            pawn_squares[BLACK].append(s)
        elif p.upper() in _ACTIVITY_DIRECTIONS:
            kind = p.upper()
            color = WHITE if p.isupper() else BLACK
            index = _ACTIVITY_INDEX_KIND.index(kind)
            pieces[color].append((s, index, 0))
    return _attack_activity_parts(board, pieces, pawn_squares)


# ──────────────────────────── 선택적 주도권 평가 (v0.4.6 계산 최적화, 기본 OFF) ────────────────────────────
# '공격하고 있는 기물의 개수'가 아니라 상대 가치 높은 기물에 당장 가해지는
# 구체적인 낮은 가치 기물의 위협을 계산한다. 최대 36cp MG / 12cp EG.
# 핀, 실제 합법 포획, 전술적 교환 결과는 계산하지 않는다: 수순 탐색이 맡는다.
# 기물 희생 자체에는 어떤 보너스도 지급하지 않는다.
# Precompute valid reverse knight offsets once; direct indexing in a mailbox
# border can otherwise step beyond the 120-element array near h8/a1.
_INITIATIVE_KNIGHT_SOURCES = {
    target: tuple(source for source in SQUARES if target - source in KNIGHT_STEPS)
    for target in SQUARES
}


def _initiative_parts(board, pieces, pawn_squares):
    """Same capped direct-threat heuristic as v0.4.5, with a victim-first scan.

    A pawn can pressure an enemy minor/rook/queen; a knight or bishop can
    pressure a rook or queen, and a rook can pressure a queen. The *strongest*
    pressure is counted once per victim. Queen and equal-value attacks do not
    score. This is a static geometric heuristic, not a legal-SEE calculation.

    Scanning backwards from each eligible victim avoids all attacker×victim
    combinations and the per-evaluation dictionary used by v0.4.5. The first
    piece on each sliding ray is the only one capable of a direct attack.
    """
    b = board.board
    scores = [0, 0]
    for color in (WHITE, BLACK):
        pawn = 'P' if color == WHITE else 'p'
        knight = 'N' if color == WHITE else 'n'
        bishop = 'B' if color == WHITE else 'b'
        rook = 'R' if color == WHITE else 'r'
        total = count = 0

        for target, kind, _ in pieces[color ^ 1]:
            # kind index: bishop=0, queen=1, rook=2, knight=3.
            # Geometric pawn threats to all four non-pawn victim types.
            if color == WHITE:
                pawn_attack = b[target - 9] == pawn or b[target - 11] == pawn
            else:
                pawn_attack = b[target + 9] == pawn or b[target + 11] == pawn
            if pawn_attack:
                value = 9 if kind in (0, 3) else 12
            elif kind == 0 or kind == 3:
                # Pawn is the only sufficiently cheap attacker of a minor piece.
                continue
            else:
                value = 0
                # For a rook/queen, a knight jump may produce a forcing threat.
                for source in _INITIATIVE_KNIGHT_SOURCES[target]:
                    if b[source] == knight:
                        value = 7 if kind == 2 else 11
                        break
                if not value:
                    # First occupied square when moving outward from a victim
                    # determines whether a bishop has a clear attack ray.
                    for direction in BISHOP_DIRS:
                        square = target + direction
                        while b[square] == EMPTY:
                            square += direction
                        if b[square] == bishop:
                            value = 7 if kind == 2 else 11
                            break
                if not value and kind == 1:
                    # Only a queen is sufficiently valuable for a rook threat.
                    for direction in ROOK_DIRS:
                        square = target + direction
                        while b[square] == EMPTY:
                            square += direction
                        if b[square] == rook:
                            value = 11
                            break
            if value:
                total += value
                count += 1

        if count:
            scores[color] = min(INITIATIVE_CAP, total + 3 * (count - 1))
    result = scores[WHITE] - scores[BLACK]
    return result, result // 3 if result >= 0 else -(-result // 3)


def initiative_terms(board):
    """독립 호출용: 합법성 판정 없이 기물 위협의 정적 보너스만 반환."""
    pieces = ([], [])
    pawn_squares = ([], [])
    for s in SQUARES:
        p = board.board[s]
        if p in 'Pp':
            pawn_squares[WHITE if p == 'P' else BLACK].append(s)
        elif p.upper() in _KIND_INDEX:
            c = WHITE if p.isupper() else BLACK
            pieces[c].append(_PIECE_AT[p.upper()][s])
    return _initiative_parts(board, pieces, pawn_squares)


# ──────────────────────────── 미리 계산해 두기 ────────────────────────────
# 평가함수는 탐색 중 수십만 번 불리므로, 기물 문자 → 120칸 점수 리스트를 미리 만들어
# 실행 중에는 인덱스 한 번으로 끝나게 합니다. 흑은 표를 위아래로 뒤집어 씁니다.
def _table_index(s, color):
    f, r = (s - 21) % 10, rank_of(s)
    return (7 - r) * 8 + f if color == WHITE else r * 8 + f


PST_MG, PST_EG, VALUE, PHASE, COLOR, KIND = {}, {}, {}, {}, {}, {}
for _kind, (_mg, _eg) in TABLES.items():
    for _p, _c in ((_kind, WHITE), (_kind.lower(), BLACK)):
        PST_MG[_p] = [0] * 120
        PST_EG[_p] = [0] * 120
        for _s in SQUARES:
            PST_MG[_p][_s] = _mg[_table_index(_s, _c)]
            PST_EG[_p][_s] = _eg[_table_index(_s, _c)]
        VALUE[_p] = PIECE_VALUE[_kind]
        PHASE[_p] = PHASE_WEIGHT.get(_kind, 0)
        COLOR[_p] = _c
        KIND[_p] = _kind


# ──────────────────────────── 평가 ────────────────────────────
def _pawn_structure(pawns):
    """pawns[color] = 폰 칸 리스트 → 백 기준 (중반, 종반) 점수"""
    # 파일별 폰 개수 / 가장 낮은·높은 랭크 (파일 인덱스 1..8, 0과 9는 양옆 패딩)
    count = [[0] * 10, [0] * 10]
    lo = [[8] * 10, [8] * 10]
    hi = [[-1] * 10, [-1] * 10]
    for c in (WHITE, BLACK):
        for s in pawns[c]:
            f, r = (s - 21) % 10 + 1, rank_of(s)
            count[c][f] += 1
            lo[c][f] = min(lo[c][f], r)
            hi[c][f] = max(hi[c][f], r)

    mg = eg = 0
    for c, sign in ((WHITE, 1), (BLACK, -1)):
        them = c ^ 1
        for f in range(1, 9):
            if count[c][f] > 1:
                mg += sign * DOUBLED[0] * (count[c][f] - 1)
                eg += sign * DOUBLED[1] * (count[c][f] - 1)
        for s in pawns[c]:
            f, r = (s - 21) % 10 + 1, rank_of(s)
            if count[c][f - 1] == 0 and count[c][f + 1] == 0:
                mg += sign * ISOLATED[0]
                eg += sign * ISOLATED[1]
            if c == WHITE:   # 앞쪽(랭크가 더 높은 곳)에 흑 폰이 없고, 내가 이 파일의 맨 앞 폰
                passed = hi[c][f] == r and all(hi[them][ff] <= r for ff in (f - 1, f, f + 1))
                rel = r
            else:            # 흑은 앞쪽이 랭크가 더 낮은 곳
                passed = lo[c][f] == r and all(lo[them][ff] >= r for ff in (f - 1, f, f + 1))
                rel = 7 - r
            if passed:
                mg += sign * PASSED_MG[rel]
                eg += sign * PASSED_EG[rel]
    return mg, eg


def _on_board(s):
    return 21 <= s <= 98 and 1 <= s % 10 <= 8


def _zone(k):
    """킹 구역: 킹 칸과 주변 칸 (판 밖은 제외)"""
    return [k] + [k + d for d in KING_STEPS if _on_board(k + d)]

# v0.4.4: 움직이지 않는 킹의 정적 구역은 한 번만 계산.
_KING_ZONES = {k: frozenset(_zone(k)) for k in SQUARES}


# 킹 칸마다 미리 계산 (평가 때는 표 조회만): 구역 / 기물 종류별로 '빈 판이라면 구역에 닿을 수 있는 칸'과
# 그때 걸어갈 방향들. REACH[킹 칸][종류 번호][기물 칸] → 방향 튜플 (나이트는 빈 튜플 = 닿음).
# 종류 번호: 0 비숍, 1 퀸, 2 룩, 3 나이트. 64 × 64칸, 불러올 때 한 번만.
_KIND_INDEX = {'B': 0, 'Q': 1, 'R': 2, 'N': 3}
ZONE, REACH = {}, {}
for _k in SQUARES:
    _z = frozenset(_zone(_k))
    ZONE[_k] = _z
    _reach = ({}, {}, {}, {})
    for _s in {z + d for z in _z for d in KNIGHT_STEPS if _on_board(z + d)}:
        _reach[3][_s] = ()
    for _s in SQUARES:
        _dirs = []
        for _group in (BISHOP_DIRS, ROOK_DIRS):
            _ok = []
            for _d in _group:
                _t = _s + _d
                while _on_board(_t) and _t not in _z:
                    _t += _d
                if _on_board(_t):
                    _ok.append(_d)
            _dirs.append(tuple(_ok))
        if _dirs[0]:
            _reach[0][_s] = _dirs[0]
        if _dirs[1]:
            _reach[2][_s] = _dirs[1]
        if _dirs[0] or _dirs[1]:
            _reach[1][_s] = _dirs[0] + _dirs[1]
    REACH[_k] = _reach
# (칸, 종류 번호, 공격 단위) — 평가 중에 튜플을 새로 만들지 않도록 미리 만들어 둠
_PIECE_AT = {kind: [(_s, _KIND_INDEX[kind], ATTACK_UNITS[kind]) for _s in range(120)] for kind in ATTACK_UNITS}


def _zone_hits(b, k, pieces):
    """pieces = (칸, 종류 번호, 공격 단위) 목록. 킹 k의 구역 칸을 하나라도 공격(자기 편이면 수비)하는
    기물의 공격 단위 합과 그 기물 수. 미끄러지는 기물은 구역 쪽 방향으로만 걸어 보고,
    도중에 다른 기물에 막히면 아님 (막는 기물이 구역 안이면 그 칸을 공격하는 것)."""
    zone, reach = ZONE[k], REACH[k]
    units = n = 0
    for s, ki, u in pieces:
        dirs = reach[ki].get(s)
        if dirs is None:
            continue
        if ki == 3:
            units += u
            n += 1
            continue
        for d in dirs:
            t = s + d
            while t not in zone and b[t] == EMPTY:
                t += d
            if t in zone:
                units += u
                n += 1
                break
    return units, n


def _king_attack(b, k, pieces):
    """_zone_hits와 같되 pieces가 (칸, 'N'|'B'|'R'|'Q') 목록 (테스트·도구용)."""
    return _zone_hits(b, k, [_PIECE_AT[kind][s] for s, kind in pieces])


def _files_mask(pawn_squares):
    m = 0
    for s in pawn_squares:
        m |= 1 << ((s - 21) % 10)
    return m


KING_FILES = [tuple(ff for ff in (f - 1, f, f + 1) if 0 <= ff <= 7) for f in range(8)]


def _king_structure(b, k, c, mine, theirs):
    """폰만으로 정해지는 부분 (폰 캐시에 킹 칸별로 저장): (실드 벌점, ((파일, 열린 파일 벌점), ...)).
    mine/theirs = 폰이 있는 파일의 비트마스크 (비트 0 = a파일)."""
    f = (k - 21) % 10
    rel = (k - 21) // 10 if c == WHITE else 7 - (k - 21) // 10   # 자기 진영 기준 랭크 (0 = 첫 랭크)
    fwd = 10 if c == WHITE else -10
    pawn = 'P' if c == WHITE else 'p'
    files = KING_FILES[f]
    shield = 0
    if rel <= 1 and f != 3 and f != 4:        # 측면에 숨은 킹의 폰 실드
        for ff in files:
            s1 = k + fwd + (ff - f)
            if b[s1] == pawn:
                continue
            shield += SHIELD_ADVANCED if b[s1 + fwd] == pawn else SHIELD_MISSING
    open_files = tuple((ff, HALF_OPEN_FILE if (theirs >> ff) & 1 else OPEN_FILE)
                       for ff in files if not (mine >> ff) & 1)
    return shield, open_files


def _ks_side(b, k, c, entry, enemy, own, power, heavy):
    """색 c 킹(칸 k)의 안전 점수 (c 기준, 0 이하) — 빠른 구현.
    entry = 폰 캐시 항목, enemy/own = 상대/내 나이트·비숍·룩·퀸의 (칸, 종류 번호, 공격 단위) 목록,
    power = 상대 공격력, heavy = 상대 룩·퀸 수. king_safety_detail()과 값이 같아야 함."""
    score = 0
    if power >= KS_STRUCT_POWER:
        key = k + 120 * c
        st = entry[4].get(key)
        if st is None:
            mine, theirs = (entry[2], entry[3]) if c == WHITE else (entry[3], entry[2])
            st = entry[4][key] = _king_structure(b, k, c, mine, theirs)
        raw = st[0]
        if heavy and st[1]:
            hfiles = 0                        # 상대 룩·퀸이 있는 파일
            for s, ki, u in enemy:
                if ki == 1 or ki == 2:
                    hfiles |= 1 << ((s - 21) % 10)
            for ff, pen in st[1]:
                raw += pen
                if (hfiles >> ff) & 1:
                    raw += HEAVY_ON_FILE
        if raw:
            score = -(-raw * (power if power < KS_FULL_POWER else KS_FULL_POWER) // KS_FULL_POWER)
    units, n = _zone_hits(b, k, enemy)
    if n >= 2:
        defenders = _zone_hits(b, k, own)[1]
        half = units // 2
        danger = units - (defenders if defenders < half else half)
        pen = danger * danger * 3 // 2
        score -= pen if pen < ATTACK_CAP else ATTACK_CAP
    return score


def _zone_attackers_slow(b, k, color):
    """기준 구현: 킹 구역의 각 칸에서 거꾸로 나이트·비숍·룩 움직임을 쏴서, color 쪽 기물 중
    구역을 공격(또는 수비)하는 것을 찾음 → (공격 단위 합, 기물 수). 미리 계산한 표를 쓰지 않음."""
    zone = [k] + [k + d for d in KING_STEPS if b[k + d] != ' ']
    want = (lambda p: p.isupper()) if color == WHITE else (lambda p: p.islower())
    found = set()
    for z in zone:
        for d in KNIGHT_STEPS:
            p = b[z + d]
            if p in ('N', 'n') and want(p):
                found.add(z + d)
        for dirs, kinds in ((BISHOP_DIRS, 'BQ'), (ROOK_DIRS, 'RQ')):
            for d in dirs:
                t = z + d
                while b[t] == EMPTY:
                    t += d
                p = b[t]
                if p != ' ' and p.upper() in kinds and want(p):
                    found.add(t)
    return sum(ATTACK_UNITS[b[s].upper()] for s in found), len(found)


def king_safety_detail(board):
    """킹 안전의 항목별 내역 [백 킹, 흑 킹] — 설명·검증용 느린 기준 구현 (캐시·미리 계산한 표 없이 정의대로).
    각 항목은 그 킹 쪽에서 본 값(0 이하). 백 기준 중반 점수 = 백 total − 흑 total."""
    b = board.board
    out = []
    for c in (WHITE, BLACK):
        k = board.king_sq[c]
        theirs = 'nbrq' if c == WHITE else 'NBRQ'
        enemy = [(s, b[s].upper()) for s in SQUARES if b[s] in theirs]
        power = sum(ATTACK_UNITS[kind] for _, kind in enemy)
        heavy_files = {(s - 21) % 10 for s, kind in enemy if kind in 'RQ'}
        d = {'power': power, 'shield': 0, 'files': 0, 'heavy_on_file': 0, 'structure': 0,
             'attackers': 0, 'units': 0, 'defenders': 0, 'attack': 0, 'total': 0}
        out.append(d)
        if power < KS_MIN_POWER:
            continue
        f, r = (k - 21) % 10, (k - 21) // 10
        rel = r if c == WHITE else 7 - r
        fwd = 10 if c == WHITE else -10
        pawn, epawn = ('P', 'p') if c == WHITE else ('p', 'P')
        files = [ff for ff in (f - 1, f, f + 1) if 0 <= ff <= 7]
        if power >= KS_STRUCT_POWER:
            if rel <= 1 and f not in (3, 4):
                for ff in files:
                    s1 = k + fwd + (ff - f)
                    if b[s1] != pawn:
                        d['shield'] += SHIELD_ADVANCED if b[s1 + fwd] == pawn else SHIELD_MISSING
            if heavy_files:
                for ff in files:
                    column = [b[sq(ff, rr)] for rr in range(8)]
                    if pawn not in column:
                        d['files'] += HALF_OPEN_FILE if epawn in column else OPEN_FILE
                        if ff in heavy_files:
                            d['heavy_on_file'] += HEAVY_ON_FILE
            raw = d['shield'] + d['files'] + d['heavy_on_file']
            d['structure'] = -(-raw * min(power, KS_FULL_POWER) // KS_FULL_POWER)
        d['units'], d['attackers'] = _zone_attackers_slow(b, k, c ^ 1)
        if d['attackers'] >= 2:
            d['defenders'] = _zone_attackers_slow(b, k, c)[1]
            danger = d['units'] - min(d['defenders'], d['units'] // 2)
            d['attack'] = -min(danger * danger * 3 // 2, ATTACK_CAP)
        d['total'] = d['structure'] + d['attack']
    return out


def eval_terms(board):
    """항목별 백 기준 (중반, 종반) 점수와 phase를 돌려줌. 설명·검증용 (느린 기준 경로).
    탐색은 evaluate_white()의 빠른 경로를 쓰고, 두 경로의 값이 같은지는 테스트가 확인함."""
    b = board.board
    material = 0
    pos_mg = pos_eg = 0
    phase = 0
    pawns = ([], [])
    bishops = [0, 0]
    for s in SQUARES:
        p = b[s]
        if p == EMPTY:
            continue
        sign = 1 if COLOR[p] == WHITE else -1
        material += sign * VALUE[p]
        pos_mg += sign * PST_MG[p][s]
        pos_eg += sign * PST_EG[p][s]
        phase += PHASE[p]
        if p == 'P' or p == 'p':
            pawns[COLOR[p]].append(s)
        elif p == 'B' or p == 'b':
            bishops[COLOR[p]] += 1

    pawn_mg, pawn_eg = _pawn_structure(pawns)
    pair = (bishops[WHITE] >= 2) - (bishops[BLACK] >= 2)
    terms = {
        '기물 가치': (material, material),
        '위치 점수': (pos_mg, pos_eg),
        '폰 구조': (pawn_mg, pawn_eg),
        '비숍 쌍': (pair * BISHOP_PAIR[0], pair * BISHOP_PAIR[1]),
    }
    if KING_SAFETY:
        w, bl = king_safety_detail(board)
        terms['킹 안전'] = (w['total'] - bl['total'], 0)
    if ATTACK_ACTIVITY:
        terms['공격 활동성'] = attack_activity_terms(board)
    if INITIATIVE:
        terms['주도권(기물 위협)'] = initiative_terms(board)
    # 폰이 하나도 없을 때만 '기물 부족(죽은 국면)'인지 확인 (드문 경우라 비용이 거의 없음)
    dead = not pawns[WHITE] and not pawns[BLACK] and board.insufficient_material()
    return terms, min(phase, MAX_PHASE), dead  # 승격으로 퀸이 늘면 phase가 24를 넘을 수 있어서 자름


def taper(mg, eg, phase):
    total = mg * phase + eg * (MAX_PHASE - phase)
    # 주의: 파이썬의 // 는 음수를 '아래로' 내림한다 (-49.5 → -50, +49.5 → +49).
    # 그러면 백과 흑이 같은 상황에서 1점씩 다르게 평가된다. 0 쪽으로 자르도록 맞춤.
    return total // MAX_PHASE if total >= 0 else -(-total // MAX_PHASE)


# ──────────────────────────── 빠른 평가 (v0.4.2) ────────────────────────────
# 탐색이 부르는 evaluate()는 아래 빠른 경로를 씀. eval_terms()(항목별 설명용)와 값이 정확히 같아야 하며,
# test_engine.py가 수천 국면에서 둘을 비교함. 빠르게 하는 방법:
#   ① 기물 가치 + 위치 점수를 한 표로 합침 (부호 포함) → 기물당 표 조회 2번
#   ② 기물 종류별 부가 정보(phase, 비숍 수, 공격력, 룩·퀸 수)를 정수 하나에 담아 더하기 한 번으로 모음
#   ③ 폰 구조는 '폰 배치'만으로 정해지므로 폰 배치(128비트 정수)를 열쇠로 결과를 기억 (폰 캐시).
#      킹 앞 폰 실드·열린 파일도 폰 배치와 킹 칸으로 정해지므로 같은 항목 안에 킹 칸별로 기억
#   ④ 항목별 dict를 만들지 않음
_FAST, _FAST_KS = {}, {}
for _p in 'PNBRQKpnbrqk':
    _c, _kind = COLOR[_p], KIND[_p]
    _sign = 1 if _c == WHITE else -1
    _mgl, _egl = [0] * 120, [0] * 120
    for _s in SQUARES:
        _mgl[_s] = _sign * (VALUE[_p] + PST_MG[_p][_s])
        _egl[_s] = _sign * (VALUE[_p] + PST_EG[_p][_s])
    _acc = PHASE[_p]                                   # 비트 0~7: phase
    if _kind == 'B':
        _acc += 1 << (8 + 4 * _c)                      # 비트 8~11 백 비숍 수, 12~15 흑 비숍 수
    if _kind in ATTACK_UNITS:
        _acc += ATTACK_UNITS[_kind] << (16 + 8 * _c)   # 비트 16~23 백 공격력, 24~31 흑 공격력
    if _kind in 'RQ':
        _acc += 1 << (32 + 4 * _c)                     # 비트 32~35 백 룩·퀸 수, 36~39 흑 룩·퀸 수
    _pb = None
    if _kind == 'P':                                   # 폰: 칸마다 비트 하나 (백 0~63, 흑 64~127)
        _pb = [0] * 120
        for _i, _s in enumerate(SQUARES):
            _pb[_s] = 1 << (_i + 64 * _c)
    _at = _PIECE_AT.get(_kind)                         # 킹 공격 계산용 (칸, 종류 번호, 공격 단위)
    _FAST[_p] = (_mgl, _egl, _acc, _pb)
    _FAST_KS[_p] = (_mgl, _egl, _acc, _pb, _at, _c)

# 폰 캐시: 폰 배치 → [폰 구조 중반, 종반, 백 폰 파일 마스크, 흑 폰 파일 마스크, {킹 칸: 실드·열린 파일}]
#   무효화: 값이 폰 배치(와 킹 칸), 그리고 폰 구조·실드 상수에만 의존 → 대국·탐색 중에는 낡지 않음.
#           상수(DOUBLED, ISOLATED, PASSED_*, SHIELD_*, OPEN_FILE 등)를 실행 중에 바꾸면 clear_pawn_cache() 필요.
#   메모리: 실측 항목 1개 약 0.8KB (128비트 열쇠 + 값 + 킹 칸별 dict) → 한도 2만 항목이면 최대 약 15MB.
#           PAWN_CACHE_MAX개를 넘으면 통째로 비움 (다시 계산하면 되는 값이라 비워도 결과는 같음).
#   적중률(실측): 중반 깊이 5 탐색에서 95%, 종반 99%, 시작 국면 깊이 6에서 79%.
PAWN_CACHE_MAX = 20_000
_PAWN_CACHE = {}
pawn_cache_misses = [0]             # 새로 계산한 횟수 (적중률 측정용)


def clear_pawn_cache():
    _PAWN_CACHE.clear()


def _pawn_entry(b, key):
    """폰 캐시에 없을 때: 보드에서 폰을 다시 모아 계산하고 저장"""
    pawns = ([s for s in SQUARES if b[s] == 'P'], [s for s in SQUARES if b[s] == 'p'])
    mg, eg = _pawn_structure(pawns)
    if len(_PAWN_CACHE) >= PAWN_CACHE_MAX:
        _PAWN_CACHE.clear()
    e = _PAWN_CACHE[key] = (mg, eg, _files_mask(pawns[WHITE]), _files_mask(pawns[BLACK]), {})
    pawn_cache_misses[0] += 1
    return e


def evaluate_white(board):
    b = board.board
    mg = eg = acc = pm = 0
    if KING_SAFETY or ATTACK_ACTIVITY or INITIATIVE:
        fast = _FAST_KS
        pl = ([], [])
        activity_pawns = ([], []) if (ATTACK_ACTIVITY or INITIATIVE) else None  # 색별 나이트·비숍·룩·퀸 (칸, 종류 번호, 공격 단위)
        for s in SQUARES:
            p = b[s]
            if p == EMPTY:
                continue
            mgl, egl, a, pb, at, c = fast[p]
            mg += mgl[s]
            eg += egl[s]
            if pb is None:
                acc += a
                if at is not None:
                    pl[c].append(at[s])
            else:
                pm |= pb[s]
                if activity_pawns is not None:
                    activity_pawns[c].append(s)
    else:
        fast = _FAST
        pl = None
        for s in SQUARES:
            p = b[s]
            if p == EMPTY:
                continue
            mgl, egl, a, pb = fast[p]
            mg += mgl[s]
            eg += egl[s]
            if pb is None:
                acc += a
            else:
                pm |= pb[s]
    if not pm and board.insufficient_material():
        return 0                     # 어떤 수순으로도 메이트가 불가능 → 무승부
    e = _PAWN_CACHE.get(pm)
    if e is None:
        e = _pawn_entry(b, pm)
    pair = ((acc >> 8 & 15) >= 2) - ((acc >> 12 & 15) >= 2)
    mg += e[0] + pair * BISHOP_PAIR[0]
    eg += e[1] + pair * BISHOP_PAIR[1]
    if KING_SAFETY:
        wpow, bpow = acc >> 16 & 255, acc >> 24 & 255
        if bpow >= KS_MIN_POWER:     # 백 킹: 흑의 공격력이 있을 때만
            mg += _ks_side(b, board.king_sq[WHITE], WHITE, e, pl[BLACK], pl[WHITE], bpow, acc >> 36 & 15)
        if wpow >= KS_MIN_POWER:
            mg -= _ks_side(b, board.king_sq[BLACK], BLACK, e, pl[WHITE], pl[BLACK], wpow, acc >> 32 & 15)
    if ATTACK_ACTIVITY:
        activity_mg, activity_eg = _attack_activity_parts(board, pl, activity_pawns)
        mg += activity_mg
        eg += activity_eg
    if INITIATIVE:
        initiative_mg, initiative_eg = _initiative_parts(board, pl, activity_pawns)
        mg += initiative_mg
        eg += initiative_eg
    phase = acc & 255
    if phase > MAX_PHASE:
        phase = MAX_PHASE
    total = mg * phase + eg * (MAX_PHASE - phase)
    return total // MAX_PHASE if total >= 0 else -(-total // MAX_PHASE)


def evaluate_white_terms(board):
    """eval_terms()의 항목을 합쳐서 낸 값 (느린 기준 경로). evaluate_white()와 항상 같아야 함."""
    terms, phase, dead = eval_terms(board)
    if dead:
        return 0
    mg = sum(t[0] for t in terms.values())
    eg = sum(t[1] for t in terms.values())
    return taper(mg, eg, phase)


def evaluate(board):
    """둘 차례인 쪽 기준 점수 (탐색에서 사용)"""
    score = evaluate_white(board)
    return score if board.side == WHITE else -score


def explain(board, title=''):
    """평가 내역을 사람이 읽기 좋게 출력"""
    terms, phase, dead = eval_terms(board)
    if title:
        print(f"\n── {title} ──")
    print(board)
    print(f"phase {phase}/24  (중반 비중 {phase / MAX_PHASE:.0%}, 종반 비중 {1 - phase / MAX_PHASE:.0%})")
    print(f"{'항목':<8}{'중반':>8}{'종반':>8}{'반영':>8}")
    for name, (mg, eg) in terms.items():
        print(f"{name:<8}{mg:>+8}{eg:>+8}{taper(mg, eg, phase):>+8}")
    if KING_SAFETY:
        for side, d in zip(('백', '흑'), king_safety_detail(board)):
            print(f"  킹 안전 {side} 킹: 상대 공격력 {d['power']:>2} | 실드 {d['shield']:+d} 열린 파일 {d['files']:+d} "
                  f"룩·퀸 있는 파일 {d['heavy_on_file']:+d} → 폰 구조 {d['structure']:+d} | "
                  f"공격자 {d['attackers']}(단위 {d['units']}) 수비 {d['defenders']} → 공격 {d['attack']:+d} | 합 {d['total']:+d}")
    if dead:
        print("기물 부족(죽은 국면) → 무승부이므로 0점")
    print(f"→ 백 기준 {evaluate_white(board):+d} 센티폰")


def explain_king_safety(board, title=''):
    """King Safety를 끈 평가와 켠 평가의 차이를 항목별로 출력 (비교·디버깅용)"""
    global KING_SAFETY
    saved = KING_SAFETY
    try:
        KING_SAFETY = False
        off = evaluate_white(board)
        KING_SAFETY = True
        on = evaluate_white(board)
        _, phase, _ = eval_terms(board)
        w, bl = king_safety_detail(board)
    finally:
        KING_SAFETY = saved
    if title:
        print(f"── {title} ──")
    print(f"  끔 {off:+d} → 켬 {on:+d}  (차이 {on - off:+d} = 중반 점수 {w['total'] - bl['total']:+d} × phase {phase}/24)")
    for side, d in (('백', w), ('흑', bl)):
        print(f"    {side} 킹: 상대 공격력 {d['power']:>2} | 실드 {d['shield']:+d}, 열린 파일 {d['files']:+d}, "
              f"룩·퀸 있는 파일 {d['heavy_on_file']:+d} → 폰 구조 {d['structure']:+d} | "
              f"공격자 {d['attackers']}개(단위 {d['units']}), 수비 {d['defenders']}개 → 공격 {d['attack']:+d} | 합 {d['total']:+d}")
    return off, on


# ──────────────────────────── 테스트·실험 ────────────────────────────
def mirror(board):
    """색을 뒤바꾼 국면 (위아래 뒤집고 백↔흑 교체). 평가가 공정하면 점수 부호만 바뀌어야 함."""
    rows = board.fen().split()[0].split('/')
    placement = '/'.join(row.swapcase() for row in reversed(rows))
    side = 'b' if board.side == WHITE else 'w'
    castle = ''.join(sorted(board.fen().split()[2].swapcase(), key='KQkq'.index)) \
        if board.castling else '-'
    ep = board.fen().split()[3]
    if ep != '-':
        ep = ep[0] + str(9 - int(ep[1]))
    return Board(f"{placement} {side} {castle} {ep} 0 1")


def greedy_move(board):
    """1수만 내다보는 엔진: 둔 직후 평가가 가장 좋은 수를 고름 (3단계 탐색이 왜 필요한지 보여 줌)"""
    best, best_score = None, -10 ** 9
    for m in board.legal_moves():
        board.make_move(m)
        score = -evaluate(board)   # 수를 두면 차례가 넘어가므로 부호를 뒤집어 내 기준으로
        board.unmake_move()
        if score > best_score:
            best, best_score = m, score
    return best, best_score


if __name__ == '__main__':
    from perft import TESTS

    explain(Board(), "시작 국면")

    b = Board()
    for mv in 'e2e4 e7e5 g1f3 b8c6 f1c4'.split():
        b.push_uci(mv)
    explain(b, "1.e4 e5 2.Nf3 Nc6 3.Bc4 (백이 기물 하나를 더 전개)")

    explain(Board('8/5k2/8/3P4/8/8/5K2/8 w - - 0 1'), "폰 종반: 통과폰과 킹 위치가 중요해짐")

    # 대칭 테스트: 색을 뒤바꾼 국면은 점수 부호만 바뀌어야 함
    print("\n── 대칭 테스트 ──")
    fens = [START_FEN] + [fen for _, fen, _ in TESTS]
    ok = True
    for fen in fens:
        b = Board(fen)
        a, m = evaluate_white(b), evaluate_white(mirror(b))
        ok &= a == -m
        print(f"  {a:>+6} / 뒤집은 국면 {m:>+6}  {'OK' if a == -m else '비대칭!'}")
    print("  모두 통과" if ok else "  실패")

    # King Safety: 끈 평가와 켠 평가의 차이를 항목별로 (v0.4.2 공식)
    print(f"\n── King Safety: 끔 → 켬, 항목별 (백 기준. 현재 기본 설정: {'켬' if KING_SAFETY else '끔'}) ──")
    ks_fens = [
        ("안전한 캐슬링 킹", "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"),
        ("중앙 노출 킹", "r1b1r1k1/ppp1qppp/2n2n2/2b5/8/2N2N2/PPP2PPP/R1BQKB1R w KQ - 0 1"),
        ("무너진 실드", "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N1P/PPP2P2/R1BQ1RK1 w - - 0 7"),
        ("룩·퀸 공격", "r1b3rk/pppp3p/2n2n2/2b1p3/2B1P2q/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"),
        ("퀸 없는 공격 (룩 둘)", "6k1/5ppp/8/8/8/6r1/r4P1P/3R2K1 w - - 0 1"),
        ("실드 무너짐, 상대는 룩 하나", "3r2k1/5ppp/8/8/8/8/5P2/3R2K1 w - - 0 1"),
        ("교환된 종반", "8/5pk1/6p1/8/8/6P1/5PK1/8 w - - 0 1"),
        ("킹 중앙 활동 종반", "8/p4p2/1p2k3/8/8/1P2K3/P4P2/8 w - - 0 1"),
    ]
    for name, fen in ks_fens:
        b = Board(fen)
        off, on = explain_king_safety(b, name)
        saved, KING_SAFETY = KING_SAFETY, True
        if on != -evaluate_white(mirror(b)):
            print("    비대칭!")
        KING_SAFETY = saved

    # 1수만 보는 엔진의 함정
    trap = Board('rnbqkbnr/pp3ppp/2p5/3p4/8/8/PPP2PPP/RNBQKBNR w KQkq - 0 4')
    print("\n── 1수만 보는 엔진의 함정 ──")
    print(trap)
    m, s = greedy_move(trap)
    print(f"1수만 보는 엔진의 선택: {m.uci()}  (둔 직후 평가 {s:+d})")
    trap.make_move(m)
    reply, _ = greedy_move(trap)
    trap.make_move(reply)
    print(f"상대의 응수: {reply.uci()}  → 백 기준 {evaluate_white(trap):+d}")
