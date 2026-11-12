"""
board.py — 1단계: 보드 표현과 합법수 생성 (+ 3단계 해시, 종국 판정)

엔진의 '눈과 손'에 해당하는 부분입니다.
 - 국면을 메모리에 담고 (보드 표현)
 - 지금 둘 수 있는 수를 빠짐없이, 틀림없이 만들고 (수 생성)
 - 수를 두고 되돌리는 일 (make / unmake)
을 합니다. 탐색·평가가 아무리 좋아도 여기가 틀리면 엔진은 반칙을 하거나
좋은 수를 아예 보지 못합니다. 그래서 perft.py로 정답 수치와 대조해 검증합니다.

────────────────────────────────────────────────────────────
보드 표현: 10x12 메일박스(mailbox)
  64칸 체스판 둘레에 '벽' 칸(OFF)을 둘러 120칸짜리 1차원 리스트로 씁니다.

        a  b  c  d  e  f  g  h
     8 91 92 93 94 95 96 97 98
     7 81 82 83 84 85 86 87 88
     6 71 .. .. .. .. .. .. 78
     5 61 .. .. .. .. .. .. 68
     4 51 .. .. .. .. .. .. 58
     3 41 .. .. .. .. .. .. 48
     2 31 .. .. .. .. .. .. 38
     1 21 22 23 24 25 26 27 28

  위로 한 칸 = +10, 오른쪽 한 칸 = +1.
  위아래로 벽이 2줄씩 있어서 나이트가 판 밖으로 2칸 튀어나가도 벽에 닿을 뿐
  리스트 범위를 벗어나지 않습니다 → "판 안인가?" 검사를 따로 할 필요가 없습니다.

기물 표기: 백은 대문자 PNBRQK, 흑은 소문자 pnbrqk, 빈칸 '.', 벽 ' '
────────────────────────────────────────────────────────────

규칙 판정 범위 (FIDE 경기 규칙 기준)
  자동 종료 outcome()        체크메이트, 스테일메이트, 기물 부족(아래 범위), 75수 규칙, 5회 동형반복
  청구 가능 claimable_draw() 50수 규칙, 3회 동형반복
  같은 국면 판정             같은 차례 + 같은 기물 배치 + 같은 캐슬링 권리 + 같은 '실제로 가능한' 앙파상
  구현하지 않은 것            "이 수를 두면 3회 반복이 된다"는 사전 청구, 막힌 폰 사슬 같은
                             기물 부족 외의 죽은 국면, 시간패 관련 규칙
"""

import random
from typing import NamedTuple

WHITE, BLACK = 0, 1
EMPTY, OFF = '.', ' '
WHITE_PIECES = frozenset('PNBRQK')
BLACK_PIECES = frozenset('pnbrqk')
# 잡을 수 있는 상대 기물. 킹은 일부러 뺐습니다: 정상 국면에서는 킹을 잡는 상황이 생길 수 없고,
# 혹시 잘못된 국면이 들어와도 '킹을 잡는 수'가 만들어져 상태가 깨지는 일이 없게 하려는 것.
CAPTURABLE = (frozenset('pnbrq'), frozenset('PNBRQ'))   # [WHITE가 잡을 수 있는 것, BLACK이 …]

# 이동 방향 (10x12 좌표 기준)
N, S, E, W = 10, -10, 1, -1
KNIGHT_STEPS = (N + N + E, N + N + W, S + S + E, S + S + W,
                E + E + N, E + E + S, W + W + N, W + W + S)
BISHOP_DIRS = (N + E, N + W, S + E, S + W)
ROOK_DIRS = (N, S, E, W)
QUEEN_DIRS = BISHOP_DIRS + ROOK_DIRS
KING_STEPS = QUEEN_DIRS
PIECE_DIRS = {'N': KNIGHT_STEPS, 'B': BISHOP_DIRS, 'R': ROOK_DIRS, 'Q': QUEEN_DIRS, 'K': KING_STEPS}

# 캐슬링 권리 (비트 플래그)
WK, WQ, BK, BQ = 1, 2, 4, 8


def sq(file, rank):
    """file 0..7 (a..h), rank 0..7 (1..8) → 10x12 인덱스"""
    return 21 + file + 10 * rank


def sq_name(s):
    return 'abcdefgh'[(s - 21) % 10] + str((s - 21) // 10 + 1)


def parse_sq(name):
    if len(name) != 2 or name[0] not in 'abcdefgh' or name[1] not in '12345678':
        raise ValueError(f"칸 이름이 잘못됨: {name!r}")
    return sq('abcdefgh'.index(name[0]), int(name[1]) - 1)


def rank_of(s):
    return (s - 21) // 10


def file_of(s):
    return (s - 21) % 10


SQUARES = [sq(f, r) for r in range(8) for f in range(8)]  # 실제 64칸 (a1 → h8)
SQUARES_REVERSED = SQUARES[::-1]                             # h8 → a1 (흑 기물 먼저 찾을 때)

A1, B1, C1, D1, E1, F1, G1, H1 = (sq(f, 0) for f in range(8))
A8, B8, C8, D8, E8, F8, G8, H8 = (sq(f, 7) for f in range(8))

# 어떤 칸에서 말이 떠나거나 그 칸으로 말이 들어오면 사라지는 캐슬링 권리.
# 킹이 움직이면 양쪽 다, 룩이 움직이거나 잡히면 그쪽만 사라집니다.
CASTLE_MASK = [WK | WQ | BK | BQ] * 120
CASTLE_MASK[E1] &= ~(WK | WQ)
CASTLE_MASK[H1] &= ~WK
CASTLE_MASK[A1] &= ~WQ
CASTLE_MASK[E8] &= ~(BK | BQ)
CASTLE_MASK[H8] &= ~BK
CASTLE_MASK[A8] &= ~BQ

# (권리, 킹 출발, 킹 도착, 룩 칸, 비어 있어야 할 칸들, 공격받으면 안 되는 칸들)
CASTLING_RULES = {
    WHITE: [(WK, E1, G1, H1, (F1, G1), (E1, F1, G1)),
            (WQ, E1, C1, A1, (D1, C1, B1), (E1, D1, C1))],
    BLACK: [(BK, E8, G8, H8, (F8, G8), (E8, F8, G8)),
            (BQ, E8, C8, A8, (D8, C8, B8), (E8, D8, C8))],
}

START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

# ──────────────────────── Zobrist 해시 (3단계에서 추가) ────────────────────────
# 국면의 '지문'. (기물, 칸)마다 64비트 난수를 하나씩 정해 두고, 판 위 기물들의 난수를
# 전부 XOR 한 값입니다. 차례·캐슬링 권리·앙파상 칸도 난수로 섞습니다.
# XOR은 두 번 하면 원래대로 돌아오므로, 수를 둘 때 바뀐 칸만 XOR 하면 해시가 갱신됩니다.
# 쓰임새: 탐색 결과 저장소(트랜스포지션 테이블)의 열쇠, 동형반복 판정.
#
# 앙파상: FIDE 규칙에서 '같은 국면'은 둘 수 있는 수까지 같아야 합니다. 그래서 앙파상 칸은
# '실제로 합법적인 앙파상 잡기가 있을 때만' 해시에 넣습니다. 1.e4 직후처럼 잡을 폰이 없거나,
# 잡으면 내 킹이 열리는(핀) 경우에는 앙파상 칸이 없는 국면과 같은 해시가 됩니다.
_rng = random.Random(20261112)  # 시드 고정 → 실행할 때마다 같은 해시
ZOBRIST_PIECE = {p: [_rng.getrandbits(64) for _ in range(120)] for p in 'PNBRQKpnbrqk'}
ZOBRIST_SIDE = _rng.getrandbits(64)
ZOBRIST_CASTLE = [_rng.getrandbits(64) for _ in range(16)]
ZOBRIST_EP = [_rng.getrandbits(64) for _ in range(120)]

# history 튜플의 칸 위치
H_MOVE, H_PIECE, H_CAPTURED, H_CAP_SQ, H_CASTLING, H_EP, H_EP_KEY, H_HALFMOVE, H_HASH = range(9)


class Move(NamedTuple):
    frm: int
    to: int
    promo: str = ''  # 승격: 'q', 'r', 'b', 'n' / 아니면 ''

    def uci(self):
        """UCI 표기 (예: e2e4, e7e8q)"""
        return sq_name(self.frm) + sq_name(self.to) + self.promo


class Board:
    def __init__(self, fen=START_FEN):
        self.board = None
        self.set_fen(fen)

    # ──────────────────────────── FEN 입출력 ────────────────────────────
    def set_fen(self, fen):
        """FEN을 읽음. 잘못된 FEN이면 ValueError를 내고, 기존 국면은 그대로 둡니다."""
        old = self.snapshot() if self.board is not None else None
        try:
            self._load_fen(fen)
        except Exception as e:
            if old is not None:
                self.restore(old)
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"FEN을 읽을 수 없음: {fen!r} ({e})") from e

    def _load_fen(self, fen):
        if not isinstance(fen, str):
            raise ValueError("FEN은 문자열이어야 함")
        parts = fen.split()
        if not 2 <= len(parts) <= 6:
            raise ValueError(f"FEN 필드 수가 잘못됨: {fen!r}")
        parts += ['-', '-', '0', '1'][len(parts) - 2:]   # 빠진 필드 기본값

        board = [OFF] * 120
        for s in SQUARES:
            board[s] = EMPTY
        rows = parts[0].split('/')
        if len(rows) != 8:
            raise ValueError("FEN 배치에 랭크가 8개가 아님")
        for i, row in enumerate(rows):
            rank, f = 7 - i, 0
            for ch in row:
                if ch in '12345678':
                    f += int(ch)
                elif ch in WHITE_PIECES or ch in BLACK_PIECES:
                    if f > 7:
                        raise ValueError(f"{8 - i}랭크의 칸 수가 8을 넘음")
                    board[sq(f, rank)] = ch
                    f += 1
                else:
                    raise ValueError(f"FEN에 알 수 없는 문자: {ch!r}")
            if f != 8:
                raise ValueError(f"{8 - i}랭크의 칸 수가 8이 아님")

        if board.count('K') != 1 or board.count('k') != 1:
            raise ValueError("백 킹과 흑 킹이 정확히 하나씩 있어야 함")
        for f in range(8):
            if board[sq(f, 0)] in 'Pp' or board[sq(f, 7)] in 'Pp':
                raise ValueError("1랭크나 8랭크에 폰이 있을 수 없음")
        if parts[1] not in ('w', 'b'):
            raise ValueError(f"차례는 w 또는 b 여야 함: {parts[1]!r}")
        if parts[2] != '-' and (set(parts[2]) - set('KQkq') or len(set(parts[2])) != len(parts[2])):
            raise ValueError(f"캐슬링 필드가 잘못됨: {parts[2]!r}")
        try:
            halfmove, fullmove = int(parts[4]), int(parts[5])
        except ValueError:
            raise ValueError("halfmove / fullmove 는 정수여야 함") from None
        if halfmove < 0 or fullmove < 1:
            raise ValueError("halfmove ≥ 0, fullmove ≥ 1 이어야 함")

        self.board = board
        self.side = WHITE if parts[1] == 'w' else BLACK
        self.halfmove, self.fullmove = halfmove, fullmove
        self.king_sq = [board.index('K'), board.index('k')]
        self.history = []

        # 캐슬링 권리: 킹·룩이 제자리에 없으면 그 권리는 조용히 버림 (흔한 FEN 실수 보정)
        self.castling = 0
        for ch, bit, k_sq, k, r_sq, r in (('K', WK, E1, 'K', H1, 'R'), ('Q', WQ, E1, 'K', A1, 'R'),
                                          ('k', BK, E8, 'k', H8, 'r'), ('q', BQ, E8, 'k', A8, 'r')):
            if ch in parts[2] and board[k_sq] == k and board[r_sq] == r:
                self.castling |= bit

        # 앙파상 칸: 방금 두 칸 전진한 폰이 실제로 있을 때만 인정, 아니면 버림
        self.ep = 0
        if parts[3] != '-':
            ep = parse_sq(parts[3])
            if self.side == WHITE:
                ok = rank_of(ep) == 5 and board[ep - 10] == 'p' and board[ep + 10] == EMPTY
            else:
                ok = rank_of(ep) == 2 and board[ep + 10] == 'P' and board[ep - 10] == EMPTY
            if ok and board[ep] == EMPTY:
                self.ep = ep

        # 둘 차례가 아닌 쪽 킹이 공격받고 있으면 불가능한 국면 (다음 수에 킹을 잡게 됨)
        if self.is_attacked(self.king_sq[self.side ^ 1], self.side):
            raise ValueError("둘 차례가 아닌 쪽의 킹이 체크 상태인 불가능한 국면")

        self.ep_key = self._ep_hash_key()
        self.hash = self.compute_hash()

    def fen(self):
        rows = []
        for rank in range(7, -1, -1):
            row, empty = '', 0
            for f in range(8):
                p = self.board[sq(f, rank)]
                if p == EMPTY:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += p
            rows.append(row + (str(empty) if empty else ''))
        castle = ''.join(c for c, bit in zip('KQkq', (WK, WQ, BK, BQ))
                         if self.castling & bit) or '-'
        ep = sq_name(self.ep) if self.ep else '-'
        return f"{'/'.join(rows)} {'wb'[self.side]} {castle} {ep} {self.halfmove} {self.fullmove}"

    def __str__(self):
        lines = [f"{rank + 1}  " + ' '.join(self.board[sq(f, rank)] for f in range(8))
                 for rank in range(7, -1, -1)]
        lines.append("   a b c d e f g h")
        return '\n'.join(lines)

    # ──────────────────────── 상태 저장 / 복구 ────────────────────────
    def snapshot(self):
        """국면 전체를 복사해 둠 (탐색이 중간에 끊겨도 원래대로 되돌리기 위해)"""
        return (self.board[:], self.side, self.castling, self.ep, self.ep_key,
                self.halfmove, self.fullmove, self.king_sq[:], self.hash, self.history[:])

    def restore(self, state):
        (board, self.side, self.castling, self.ep, self.ep_key,
         self.halfmove, self.fullmove, king_sq, self.hash, history) = state
        # 리스트는 '제자리에서' 바꿈: 다른 곳에서 self.board 를 참조하고 있어도 같이 복구됨
        self.board[:] = board
        self.king_sq[:] = king_sq
        self.history[:] = history

    # ──────────────────────────── 해시 ────────────────────────────
    def compute_hash(self):
        """해시를 처음부터 계산 (검증용). 평소엔 make_move가 차분 갱신함."""
        h = 0
        for s in SQUARES:
            p = self.board[s]
            if p != EMPTY:
                h ^= ZOBRIST_PIECE[p][s]
        if self.side == BLACK:
            h ^= ZOBRIST_SIDE
        return h ^ ZOBRIST_CASTLE[self.castling] ^ self._ep_hash_key()

    def _ep_hash_key(self):
        """합법적인 앙파상 잡기가 실제로 있을 때만 앙파상 칸의 난수, 아니면 0"""
        ep = self.ep
        if not ep:
            return 0
        b = self.board
        if self.side == WHITE:
            pawn, victim, froms = 'P', ep - 10, (ep - 9, ep - 11)
        else:
            pawn, victim, froms = 'p', ep + 10, (ep + 9, ep + 11)
        king = self.king_sq[self.side]
        for s in froms:
            if b[s] == pawn:
                # 잡기를 흉내 내 보고(보드만 잠깐 바꿨다 되돌림) 내 킹이 공격받는지 확인
                captured = b[victim]
                b[s], b[victim], b[ep] = EMPTY, EMPTY, pawn
                exposed = self.is_attacked(king, self.side ^ 1)
                b[s], b[victim], b[ep] = pawn, captured, EMPTY
                if not exposed:
                    return ZOBRIST_EP[ep]
        return 0

    # ──────────────────────────── 공격 판정 ────────────────────────────
    def is_attacked(self, s, by):
        """칸 s를 by 쪽 기물이 공격하고 있는가?

        요령: s에서 '거꾸로' 각 기물의 움직임을 쏴 봅니다.
        s에서 나이트 점프로 닿는 칸에 상대 나이트가 있으면 s는 나이트에게 공격받는 것.
        """
        b = self.board
        if by == WHITE:
            if b[s - 9] == 'P' or b[s - 11] == 'P':  # 백 폰은 +9, +11 방향으로 잡음
                return True
            knight, bishop, rook, queen, king = 'N', 'B', 'R', 'Q', 'K'
        else:
            if b[s + 9] == 'p' or b[s + 11] == 'p':
                return True
            knight, bishop, rook, queen, king = 'n', 'b', 'r', 'q', 'k'
        for d in KNIGHT_STEPS:
            if b[s + d] == knight:
                return True
        for d in KING_STEPS:
            if b[s + d] == king:
                return True
        for d in BISHOP_DIRS:
            t = s + d
            while b[t] == EMPTY:
                t += d
            if b[t] == bishop or b[t] == queen:
                return True
        for d in ROOK_DIRS:
            t = s + d
            while b[t] == EMPTY:
                t += d
            if b[t] == rook or b[t] == queen:
                return True
        return False

    def in_check(self, color=None):
        if color is None:
            color = self.side
        return self.is_attacked(self.king_sq[color], color ^ 1)

    # ──────────────────────────── 수 생성 ────────────────────────────
    def pseudo_legal_moves(self, captures_only=False):
        """기물 움직임 규칙만 지킨 수. 자기 킹이 체크에 남는 수도 섞여 있음.
        captures_only=True면 잡는 수와 승격만 (3단계 정적 탐색용)."""
        b = self.board
        moves = []
        add = moves.append
        if self.side == WHITE:
            own, up, start_rank, last_rank = WHITE_PIECES, N, 1, 7
        else:
            own, up, start_rank, last_rank = BLACK_PIECES, S, 6, 0
        enemy = CAPTURABLE[self.side]

        for s in SQUARES:
            p = b[s]
            if p not in own:
                continue
            kind = p.upper()

            if kind == 'P':
                t = s + up
                if b[t] == EMPTY and (not captures_only or rank_of(t) == last_rank):
                    self._add_pawn_move(moves, s, t, last_rank)    # 한 칸 전진
                    if not captures_only and rank_of(s) == start_rank and b[t + up] == EMPTY:
                        add(Move(s, t + up))                       # 첫 수 두 칸 전진
                for t in (s + up + E, s + up + W):                 # 대각선 잡기 / 앙파상
                    if b[t] in enemy or t == self.ep:
                        self._add_pawn_move(moves, s, t, last_rank)

            elif kind == 'N' or kind == 'K':                       # 한 번 뛰는 기물
                for d in (KNIGHT_STEPS if kind == 'N' else KING_STEPS):
                    t = s + d
                    if b[t] in enemy or (b[t] == EMPTY and not captures_only):
                        add(Move(s, t))

            else:                                                  # 미끄러지는 기물
                for d in PIECE_DIRS[kind]:
                    t = s + d
                    while b[t] == EMPTY:
                        if not captures_only:
                            add(Move(s, t))
                        t += d
                    if b[t] in enemy:
                        add(Move(s, t))

        if not captures_only:
            self._add_castling(moves)
        return moves

    @staticmethod
    def _add_pawn_move(moves, frm, to, last_rank):
        if rank_of(to) == last_rank:
            for promo in 'qrbn':
                moves.append(Move(frm, to, promo))
        else:
            moves.append(Move(frm, to))

    def _add_castling(self, moves):
        b = self.board
        king, rook = ('K', 'R') if self.side == WHITE else ('k', 'r')
        enemy = self.side ^ 1
        for right, k_from, k_to, r_sq, must_empty, must_safe in CASTLING_RULES[self.side]:
            if (self.castling & right
                    and b[k_from] == king and b[r_sq] == rook
                    and all(b[s] == EMPTY for s in must_empty)
                    and not any(self.is_attacked(s, enemy) for s in must_safe)):
                moves.append(Move(k_from, k_to))

    def legal_moves(self):
        """수를 실제로 두어 보고 내 킹이 공격받지 않는 것만 남깁니다."""
        legal = []
        for m in self.pseudo_legal_moves():
            self.make_move(m)
            if not self.is_attacked(self.king_sq[self.side ^ 1], self.side):
                legal.append(m)
            self.unmake_move()
        return legal

    def has_legal_move(self, in_check=None):
        """합법수가 하나라도 있는가? (메이트·스테일메이트 판정용, 정적 탐색에서 자주 불림)

        모든 수를 만들지 않고 빨리 답하는 요령:
          체크가 아닐 때, 킹과 같은 가로·세로·대각선에 있지 않은 기물은 핀될 수 없으므로
          그 기물이 규칙상 움직일 수 있으면 그 수는 반드시 합법 → 바로 True.
          이 빠른 길로 답이 안 나올 때만 수를 하나씩 두어 보며 확인합니다.
        """
        if in_check is None:
            in_check = self.in_check()
        if not in_check:
            b = self.board
            side = self.side
            king = self.king_sq[side]
            kf, kr = file_of(king), rank_of(king)
            own = WHITE_PIECES if side == WHITE else BLACK_PIECES
            enemy = CAPTURABLE[side]
            up = N if side == WHITE else S
            for s in (SQUARES if side == WHITE else SQUARES_REVERSED):
                p = b[s]
                if p not in own or s == king:
                    continue
                df, dr = file_of(s) - kf, rank_of(s) - kr
                if df == 0 or dr == 0 or df == dr or df == -dr:
                    continue                      # 핀될 수도 있는 기물은 빠른 길에서 제외
                kind = p.upper()
                if kind == 'P':
                    if b[s + up] == EMPTY or b[s + up + E] in enemy or b[s + up + W] in enemy:
                        return True
                else:
                    for d in PIECE_DIRS[kind]:    # 미끄러지는 기물도 첫 칸만 보면 충분
                        if b[s + d] == EMPTY or b[s + d] in enemy:
                            return True
        # 느린 길: 하나씩 두어 보다가 합법수가 나오면 즉시 멈춤
        for m in self.pseudo_legal_moves():
            self.make_move(m)
            ok = not self.is_attacked(self.king_sq[self.side ^ 1], self.side)
            self.unmake_move()
            if ok:
                return True
        return False

    # ──────────────────────────── 두기 / 되돌리기 ────────────────────────────
    def make_move(self, m):
        """수를 둠. 속도를 위해 합법성은 검사하지 않음 → 합법수(또는 pseudo_legal_moves의 수)만 넣을 것.
        바깥 입력은 push_uci()를 쓰면 검사해 줍니다."""
        b = self.board
        frm, to, promo = m
        piece = b[frm]
        is_pawn = piece == 'P' or piece == 'p'

        cap_sq = to
        if is_pawn and to == self.ep:          # 앙파상: 잡히는 폰은 도착 칸 '뒤'에 있음
            cap_sq = to - 10 if piece == 'P' else to + 10
        captured = b[cap_sq]
        new_piece = (promo.upper() if piece == 'P' else promo) if promo else piece

        # 해시 차분 갱신 (먼저 계산 → 잘못된 수가 들어와 여기서 예외가 나도 상태는 그대로)
        zp = ZOBRIST_PIECE
        h = self.hash ^ ZOBRIST_CASTLE[self.castling] ^ self.ep_key ^ ZOBRIST_SIDE
        h ^= zp[piece][frm] ^ zp[new_piece][to]
        if captured != EMPTY:
            h ^= zp[captured][cap_sq]

        # 되돌릴 때 필요한 것만 저장 (보드 전체를 복사하지 않음)
        self.history.append((m, piece, captured, cap_sq, self.castling, self.ep,
                             self.ep_key, self.halfmove, self.hash))

        b[cap_sq] = EMPTY
        b[frm] = EMPTY
        b[to] = new_piece

        if piece == 'K' or piece == 'k':
            self.king_sq[self.side] = to
            if to - frm == 2:                  # 킹사이드 캐슬링: 룩도 옮김
                rook = b[frm + 3]
                b[frm + 1], b[frm + 3] = rook, EMPTY
                h ^= zp[rook][frm + 3] ^ zp[rook][frm + 1]
            elif frm - to == 2:                # 퀸사이드 캐슬링
                rook = b[frm - 4]
                b[frm - 1], b[frm - 4] = rook, EMPTY
                h ^= zp[rook][frm - 4] ^ zp[rook][frm - 1]

        self.castling &= CASTLE_MASK[frm] & CASTLE_MASK[to]
        self.ep = (frm + to) // 2 if is_pawn and abs(to - frm) == 20 else 0
        self.halfmove = 0 if is_pawn or captured != EMPTY else self.halfmove + 1
        if self.side == BLACK:
            self.fullmove += 1
        self.side ^= 1
        # 앙파상 해시는 '이제 둘 차례인 쪽'이 실제로 잡을 수 있는지에 달려 있어서 차례를 바꾼 뒤 계산
        self.ep_key = self._ep_hash_key() if self.ep else 0
        self.hash = h ^ ZOBRIST_CASTLE[self.castling] ^ self.ep_key

    def unmake_move(self):
        (m, piece, captured, cap_sq, castling, ep, ep_key,
         halfmove, self.hash) = self.history.pop()
        frm, to, _ = m
        b = self.board
        self.side ^= 1
        if self.side == BLACK:
            self.fullmove -= 1
        b[to] = EMPTY
        b[cap_sq] = captured
        b[frm] = piece                         # 승격했어도 원래 폰으로 복구됨
        if piece == 'K' or piece == 'k':
            self.king_sq[self.side] = frm
            if to - frm == 2:
                b[frm + 3], b[frm + 1] = b[frm + 1], EMPTY
            elif frm - to == 2:
                b[frm - 4], b[frm - 1] = b[frm - 1], EMPTY
        self.castling, self.ep, self.ep_key, self.halfmove = castling, ep, ep_key, halfmove

    # ──────────────────────────── 편의 기능 ────────────────────────────
    def parse_uci(self, text):
        """'e2e4' 같은 문자열을 합법수 Move로 바꿈. 불법이거나 형식이 틀리면 None."""
        if not isinstance(text, str):
            return None
        text = text.strip().lower()
        for m in self.legal_moves():
            if m.uci() == text:
                return m
        return None

    def push_uci(self, text):
        m = self.parse_uci(text)
        if m is None:
            raise ValueError(f"불법수: {text}")
        self.make_move(m)
        return m

    # ──────────────────────── 무승부·종국 판정 ────────────────────────
    def _same_side_hashes(self):
        """지금과 같은 차례였던 과거 국면들의 해시 (마지막 폰 이동/잡기 이후만, 최근 것부터)"""
        n = len(self.history)
        stop = max(0, n - self.halfmove)
        return (self.history[k][H_HASH] for k in range(n - 2, stop - 1, -2))

    def repetition_count(self):
        """지금 국면이 (지금 포함) 몇 번 나왔는가"""
        h = self.hash
        return 1 + sum(1 for x in self._same_side_hashes() if x == h)

    def insufficient_material(self):
        """기물 부족으로 어떤 수순으로도 메이트가 불가능한가? (FIDE 5.2.2 '죽은 국면' 중 기물 조합만)

        죽은 국면:  킹 대 킹 / 킹+나이트 하나 대 킹 / 킹+비숍 하나 대 킹 /
                   남은 기물이 모두 비숍이고 전부 같은 색 칸에 있음 (양쪽 합쳐서, 개수 무관)
        죽은 국면 아님 (상대가 협조하면 메이트 가능): 나이트 2개 대 킹, 나이트 대 나이트,
                   비숍 대 나이트, 다른 색 칸 비숍끼리, 폰·룩·퀸이 하나라도 있는 경우
        """
        minors = []
        for s in SQUARES:
            p = self.board[s]
            if p == EMPTY or p == 'K' or p == 'k':
                continue
            if p not in 'NBnb':
                return False                     # 폰·룩·퀸이 있으면 메이트 가능
            minors.append((p, s))
        if len(minors) <= 1:
            return True
        if all(p in 'Bb' for p, _ in minors):
            colors = {(file_of(s) + rank_of(s)) % 2 for _, s in minors}
            return len(colors) == 1
        return False

    def outcome(self):
        """규칙상 '자동으로' 대국이 끝났으면 (결과, 사유), 아니면 None.
        우선순위: 체크메이트·스테일메이트가 다른 무승부 규칙보다 먼저 (FIDE 9.6.2: 75수째 수가
        메이트면 메이트가 우선)."""
        in_check = self.in_check()
        if not self.has_legal_move(in_check):
            if in_check:
                return ('0-1' if self.side == WHITE else '1-0'), '체크메이트'
            return '1/2-1/2', '스테일메이트'
        if self.insufficient_material():
            return '1/2-1/2', '기물 부족(죽은 국면)'
        if self.halfmove >= 150:
            return '1/2-1/2', '75수 규칙'
        if self.repetition_count() >= 5:
            return '1/2-1/2', '5회 동형반복'
        return None

    def claimable_draw(self):
        """선수가 청구하면 무승부가 되는 사유 (FIDE 9.2, 9.3), 없으면 None.
        한계: '이 수를 두면 3회째가 된다'고 수를 두기 전에 청구하는 경우는 다루지 않음."""
        if self.halfmove >= 100:
            return '50수 규칙'
        if self.repetition_count() >= 3:
            return '3회 동형반복'
        return None


if __name__ == '__main__':
    b = Board()
    print(b)
    print("FEN:", b.fen())
    moves = b.legal_moves()
    print(f"합법수 {len(moves)}개:", ' '.join(m.uci() for m in moves))
    for mv in ('e2e4', 'e7e5', 'g1f3'):
        b.push_uci(mv)
    print("\n1.e4 e5 2.Nf3 이후\n" + str(b))
    print("FEN:", b.fen())
