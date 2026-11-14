"""v0.4.6: exact Initiative behavior vs the independent v0.4.5 threat oracle.

Pure standard library. Tests optimize calculation only; they do not establish Elo
or a human/Tal-like playing style.
"""
import random
import unittest
from pathlib import Path

import evaluate
from board import Board, EMPTY, START_FEN, SQUARES, WHITE, BLACK, KNIGHT_STEPS, BISHOP_DIRS, ROOK_DIRS
from evaluate import evaluate_white, evaluate_white_terms, initiative_terms, mirror
from search import Searcher, MATE
from analyze_sacrifices import score_gap_label, stockfish_review


# The previous code compared every attacker with every more valuable opponent.
# This test-only implementation deliberately uses that old direction of search,
# rather than importing the new reverse/victim-based helper.
_INDEX_VALUE = (330, 900, 500, 320)  # B Q R N
_REF_KNIGHT_STEPS = frozenset(KNIGHT_STEPS)
_REF_BISHOP_DIRS = frozenset(BISHOP_DIRS)
_REF_ROOK_DIRS = frozenset(ROOK_DIRS)
_RAY = [[0] * 120 for _ in range(120)]
for source in SQUARES:
    for direction in BISHOP_DIRS + ROOK_DIRS:
        t = source + direction
        while 21 <= t <= 98 and 1 <= t % 10 <= 8:
            _RAY[source][t] = direction
            t += direction


def initiative_v045_oracle(board):
    """Original geometric material-threat scoring (uncapped per target, capped per side)."""
    b = board.board
    pawns = ([], [])
    pieces = ([], [])
    idx = {'B': 0, 'Q': 1, 'R': 2, 'N': 3}
    for s in SQUARES:
        p = b[s]
        if p == 'P':
            pawns[WHITE].append(s)
        elif p == 'p':
            pawns[BLACK].append(s)
        elif p.upper() in idx:
            pieces[WHITE if p.isupper() else BLACK].append((s, idx[p.upper()]))
    scores = [0, 0]
    for color in (WHITE, BLACK):
        enemy = 'nbrq' if color == WHITE else 'NBRQ'
        threatened = {}
        for source in pawns[color]:
            for t in evaluate._ACTIVITY_PAWN_TARGETS[color][source]:
                if b[t] in enemy:
                    threatened[t] = max(threatened.get(t, 0), 9 if b[t].upper() in 'NB' else 12)
        for source, attacker_idx in pieces[color]:
            if attacker_idx == 1:  # no nonking target costlier than queen
                continue
            for t, target_idx in pieces[color ^ 1]:
                gain = _INDEX_VALUE[target_idx] - _INDEX_VALUE[attacker_idx]
                if gain < 150:
                    continue
                if attacker_idx == 3:
                    if t - source not in KNIGHT_STEPS:
                        continue
                else:
                    direction = _RAY[source][t]
                    if not direction:
                        continue
                    if attacker_idx == 0 and direction not in BISHOP_DIRS:
                        continue
                    if attacker_idx == 2 and direction not in ROOK_DIRS:
                        continue
                    square = source + direction
                    while square != t and b[square] == EMPTY:
                        square += direction
                    if square != t:
                        continue
                threatened[t] = max(threatened.get(t, 0), 7 if gain < 400 else 11)
        if threatened:
            scores[color] = min(evaluate.INITIATIVE_CAP,
                                sum(threatened.values()) + 3 * (len(threatened) - 1))
    result = scores[WHITE] - scores[BLACK]
    return result, result // 3 if result >= 0 else -(-result // 3)


# v0.4.5 production implementation, retained ONLY as a test/benchmark oracle.
def initiative_v045_fast(board, pieces, pawn_squares):
    """가치 높은 적 기물에 대한 직접 압박을 백 기준 (중반, 종반)으로 환산.

    이미 계산한 기물 위치/폰 위치를 활용. 상대의 더 비싼 기물만을 대상으로
    선별하므로 비싼 기물 이동칸 전체를 생성하지 않음. 대상별 최대 위협만 셈.
    """
    b = board.board
    scores = [0, 0]
    for c in (WHITE, BLACK):
        enemy = 'nbrq' if c == WHITE else 'NBRQ'
        threatened = {}  # attacked target square -> highest tactical-pressure score
        for s in pawn_squares[c]:
            for t in evaluate._ACTIVITY_PAWN_TARGETS[c][s]:
                if b[t] in enemy:
                    threatened[t] = max(threatened.get(t, 0), 9 if b[t].upper() in 'NB' else 12)
        targets = pieces[c ^ 1]
        for s, ki, _ in pieces[c]:
            attacker = _INDEX_VALUE[ki]
            if ki == 1:  # 퀸은 더 비싼 비킹 기물이 없으므로 skip
                continue
            for t, ti, _ in targets:
                gain = _INDEX_VALUE[ti] - attacker
                if gain < 150:
                    continue
                if ki == 3:  # knight is leaper
                    if t - s not in _REF_KNIGHT_STEPS:
                        continue
                else:
                    direction = _RAY[s][t]
                    if not direction:
                        continue
                    if ki == 0 and direction not in _REF_BISHOP_DIRS:
                        continue
                    if ki == 2 and direction not in _REF_ROOK_DIRS:
                        continue
                    block = s + direction
                    while block != t and b[block] == EMPTY:
                        block += direction
                    if block != t:
                        continue
                threatened[t] = max(threatened.get(t, 0), 7 if gain < 400 else 11)
        if threatened:
            scores[c] = min(evaluate.INITIATIVE_CAP, sum(threatened.values()) + 3 * (len(threatened) - 1))
    result = scores[WHITE] - scores[BLACK]
    return result, result // 3 if result >= 0 else -(-result // 3)




def initiative_v045_adapter(board, pieces, pawn_squares):
    # Same v0.4.5 interface as the new implementation; no rescanning overhead.
    return initiative_v045_fast(board, pieces, pawn_squares)


def sample_fens():
    """Fixed fixture, random legal play, promotions and mirror positions."""
    path = Path(__file__).with_name('v044_positions.txt')
    fens = [START_FEN]
    fens += [x for x in path.read_text().splitlines() if x and not x.startswith('#')]
    fens += [
        '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1',
        '8/5P1k/5K2/8/8/8/8/8 w - - 0 1',
        '8/8/8/8/8/5kr1/5p1K/6r1 b - - 0 1',
        '4k3/P7/8/8/8/8/1p6/4K3 w - - 0 1',
        '7k/8/6K1/8/8/8/8/R7 w - - 0 1',
    ]
    rng = random.Random(46061)
    seeds = [START_FEN, fens[1], fens[len(fens)//2], fens[-4]]
    for g in range(14):
        b = Board(seeds[g % len(seeds)])
        for _ in range(68):
            moves = b.legal_moves()
            if not moves or b.outcome():
                break
            b.make_move(rng.choice(moves))
            fens.append(b.fen())
    return fens


class InitiativeV046Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fens = sample_fens()

    def setUp(self):
        self.original = evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY, evaluate.KING_SAFETY

    def tearDown(self):
        evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY, evaluate.KING_SAFETY = self.original

    def test_exact_score_equivalence(self):
        """Same scoring rule over a broad range; must not subtly change play."""
        for fen in self.fens:
            b = Board(fen)
            self.assertEqual(initiative_v045_oracle(b), initiative_terms(b), fen)
            pieces = ([], [])
            pawns = ([], [])
            for sq in SQUARES:
                piece = b.board[sq]
                if piece in 'Pp':
                    pawns[WHITE if piece == 'P' else BLACK].append(sq)
                elif piece.upper() in 'BNRQ':
                    color = WHITE if piece.isupper() else BLACK
                    pieces[color].append((sq, {'B': 0, 'Q': 1, 'R': 2, 'N': 3}[piece.upper()], 0))
            self.assertEqual(initiative_v045_fast(b, pieces, pawns), initiative_terms(b), fen)

    def test_mirror_equivalence(self):
        for fen in self.fens[::4]:
            b = Board(fen)
            self.assertEqual(initiative_terms(b),
                             tuple(-v for v in initiative_terms(mirror(b))), fen)

    def test_all_features_fast_slow(self):
        for initiative in (False, True):
            for activity in (False, True):
                for safety in (False, True):
                    evaluate.INITIATIVE = initiative
                    evaluate.ATTACK_ACTIVITY = activity
                    evaluate.KING_SAFETY = safety
                    for fen in self.fens[::18]:
                        b = Board(fen)
                        self.assertEqual(evaluate_white(b), evaluate_white_terms(b),
                                         (initiative, activity, safety, fen))

    def test_knight_source_bounds(self):
        """No 120-square mailbox overflow from reverse knight lookups."""
        for dest, sources in evaluate._INITIATIVE_KNIGHT_SOURCES.items():
            self.assertEqual(set(sources),
                             {s for s in SQUARES if dest - s in KNIGHT_STEPS})
        for fen in self.fens:
            self.assertIsInstance(initiative_terms(Board(fen)), tuple)

    def test_search_equivalence(self):
        evaluate.INITIATIVE = True
        evaluate.ATTACK_ACTIVITY = False
        evaluate.KING_SAFETY = False
        cases = [START_FEN] + self.fens[1:][::max(1, len(self.fens)//10)][:9]
        new_func = evaluate._initiative_parts
        try:
            for fen in cases:
                b = Board(fen)
                snapshot = b.snapshot()
                evaluate._initiative_parts = initiative_v045_adapter
                before = Searcher(tt_size=3000).search(b, max_depth=3, on_info=None)
                evaluate._initiative_parts = new_func
                after = Searcher(tt_size=3000).search(b, max_depth=3, on_info=None)
                self.assertEqual(before, after, fen)
                self.assertEqual(snapshot, b.snapshot(), fen)
        finally:
            evaluate._initiative_parts = new_func

    def test_sacrifice_score_gap_not_falsely_centipawns(self):
        self.assertIn('mate-sensitive', score_gap_label(MATE - 1, 0))
        self.assertEqual(score_gap_label(100, 30), '70cp')

    def test_stockfish_crosscheck_is_explicitly_optional(self):
        fen = '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'
        with self.assertRaises(RuntimeError):
            stockfish_review(Board(fen), ['f7f8n'], '/path/that/does/not/exist', 8)

    def test_tactical_regression_with_ini_enabled(self):
        evaluate.INITIATIVE = True
        b = Board('6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1')
        old = b.snapshot()
        for qc in (False, True):
            s = Searcher(tt_size=3000)
            s.qsearch_quiet_checks = qc
            move, score = s.search(b, max_depth=2, on_info=None)
            self.assertEqual((move.uci(), score), ('f7f8n', MATE - 1))
            self.assertEqual(b.snapshot(), old)


if __name__ == '__main__':
    unittest.main(verbosity=2)
