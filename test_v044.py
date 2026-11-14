"""v0.4.4 quality checks: quiet-check prefilter, independent oracle, attack activity.

Run: python test_v044.py
The reference qsearch deliberately enumerates ALL legal moves rather than using the
optimized pseudo-legal filter. Board and move rules are still shared; this is
independent candidate-selection validation, not an independent chess rules engine.
"""
import io
import random
import unittest
from pathlib import Path

import evaluate
from board import Board, EMPTY, WHITE
from evaluate import attack_activity_terms, evaluate_white, evaluate_white_terms, mirror
from search import INF, MATE, Searcher, TimeUp
from uci import UCIEngine

HERE = Path(__file__).resolve().parent
CASE_FENS = [x for x in (HERE / 'v044_positions.txt').read_text().splitlines()
             if x and not x.startswith('#')]
SYNTHETIC = [
    '7k/8/6K1/8/8/8/8/R7 w - - 0 1',
    '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1',
    '5r2/4P1K1/4k3/2Q5/8/8/8/8 w - - 0 1',
    '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1',
    '4k3/8/8/8/8/8/4B3/4R1K1 w - - 0 1',
    '7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1',
    '5k2/8/8/8/8/8/8/4K2R w K - 0 1',  # O-O → Rf1+ (castling rook check)
]


def ref_quiesce(b, alpha, beta, ply=0, allow_quiet_check=True):
    """Small oracle: full legal move list, assess captures/quiet checks *after* move.

    No use of Searcher's prefilter, quiescence code, move ordering, or TT.
    For test FENs, halfmove is reset to 0 and there are no pre-root repetitions.
    """
    moves = b.legal_moves()
    in_check = b.in_check()
    if not moves:
        return -MATE + ply if in_check else 0
    if ply >= 100:
        return evaluate.evaluate(b)
    if in_check:
        best = -INF
    else:
        best = evaluate.evaluate(b)
        if best >= beta:
            return best
        alpha = max(alpha, best)

    for m in moves:
        tactical = (b.board[m.to] != EMPTY or bool(m.promo) or
                    (m.to == b.ep and b.board[m.frm] in 'Pp'))
        if not in_check and not tactical and not allow_quiet_check:
            continue
        b.make_move(m)
        try:
            if not in_check and not tactical and not b.in_check():
                continue
            score = -ref_quiesce(b, -beta, -alpha, ply + 1, False)
        finally:
            b.unmake_move()
        best = max(best, score)
        alpha = max(alpha, best)
        if alpha >= beta:
            break
    return best


class CheckCandidateTests(unittest.TestCase):
    def test_no_missed_quiet_checks_on_game_positions(self):
        engine = Searcher(tt_size=0)
        missed = []
        count = candidates = checks = 0
        for f in CASE_FENS + SYNTHETIC:
            b = Board(f)
            state = b.snapshot()
            filtered = set(engine._quiet_check_candidates(b))
            for m in b.pseudo_legal_moves():
                piece = b.board[m.frm]
                if b.board[m.to] != EMPTY or m.promo or (m.to == b.ep and piece in 'Pp'):
                    continue
                count += 1
                candidates += m in filtered
                b.make_move(m)
                try:
                    actual = not b.in_check(b.side ^ 1) and b.in_check()
                finally:
                    b.unmake_move()
                if actual:
                    checks += 1
                    if m not in filtered:
                        missed.append((f, m.uci()))
            self.assertEqual(b.snapshot(), state)
        self.assertFalse(missed, missed[:6])
        self.assertGreater(checks, 40)
        # The prefilter must be materially more selective than blindly trying all quiet moves.
        self.assertLess(candidates * 2, count)

    def test_same_qscore_with_and_without_prefilter(self):
        fens = SYNTHETIC + CASE_FENS[::7]
        for fen in fens:
            b = Board(fen)
            snap = b.snapshot()
            results = []
            for use_filter in (False, True):
                s = Searcher(tt_size=0)
                s.qsearch_quiet_checks = True
                s.qsearch_fast_checks = use_filter
                results.append(s.quiesce(b, -INF, INF, 0))
                self.assertEqual(b.snapshot(), snap)
            self.assertEqual(results[0], results[1], (fen, results))

    def test_reference_full_legal_move_oracle(self):
        for fen in SYNTHETIC + CASE_FENS[:10]:
            b = Board(fen)
            state = b.snapshot()
            oracle = ref_quiesce(b, -INF, INF)
            self.assertEqual(b.snapshot(), state)
            s = Searcher(tt_size=0)
            s.qsearch_quiet_checks = True
            got = s.quiesce(b, -INF, INF, 0)
            self.assertEqual(oracle, got, (fen, oracle, got))
            self.assertEqual(b.snapshot(), state)

    def test_castling_rook_quiet_check(self):
        fen = SYNTHETIC[-1]
        b = Board(fen)
        m = b.parse_uci('e1g1')
        self.assertIsNotNone(m)
        s = Searcher(tt_size=0)
        self.assertIn(m, set(s._quiet_check_candidates(b)))
        b.make_move(m)
        self.assertTrue(b.in_check())
        b.unmake_move()
        self.assertEqual(b.fen(), fen)

    def test_limit_interrupt_restores_board(self):
        b = Board(SYNTHETIC[-1]); snap=b.snapshot()
        s=Searcher(tt_size=0);s.qsearch_quiet_checks=True;s.node_limit=2;s._next_check=2
        with self.assertRaises(TimeUp):
            s.quiesce(b,-INF,INF,0)
        self.assertEqual(b.snapshot(),snap)


class AttackActivityTests(unittest.TestCase):
    def setUp(self):
        self.old_act = evaluate.ATTACK_ACTIVITY
        self.old_ks = evaluate.KING_SAFETY
        evaluate.ATTACK_ACTIVITY = True

    def tearDown(self):
        evaluate.ATTACK_ACTIVITY = self.old_act
        evaluate.KING_SAFETY = self.old_ks

    def test_symmetry_and_fast_slow_path(self):
        for king in (False, True):
            evaluate.KING_SAFETY = king
            for fen in SYNTHETIC + CASE_FENS[::3]:
                board=Board(fen)
                a=evaluate_white(board)
                self.assertEqual(a, evaluate_white_terms(board), fen)
                self.assertEqual(a, -evaluate_white(mirror(board)), fen)

    def test_start_position_zero_and_active_knight(self):
        self.assertEqual(attack_activity_terms(Board())[0],0)
        centralized=Board('6k1/8/8/3N4/8/8/8/6K1 w - - 0 1')
        corner=Board('6k1/8/8/8/8/8/8/N5K1 w - - 0 1')
        self.assertGreater(attack_activity_terms(centralized)[0], attack_activity_terms(corner)[0])

    def test_uci_subprocess_toggle(self):
        # External GUI-like process, not merely toggling a Python global in-process.
        from test_uci import Engine
        e = Engine()
        try:
            e.send('uci')
            line, got, _ = e.wait_for(lambda x: x == 'uciok', 5)
            self.assertEqual(line, 'uciok')
            self.assertIn('option name AttackActivity type check default false', got)
            fen = 'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4'
            e.send('position fen ' + fen)
            scores = []
            for flag in ('false', 'true', 'false'):
                e.send('setoption name AttackActivity value ' + flag)
                e.send('go depth 2')
                mv, got, _ = e.bestmove(10)
                self.assertIsNotNone(Board(fen).parse_uci(mv))
                infos = [l for l in got if l.startswith('info depth 2 ')]
                self.assertTrue(infos, (flag, got))
                scores.append(infos[-1].split('score cp ')[-1].split()[0])
            self.assertEqual(scores[0], scores[2], scores)
        finally:
            e.close()
            if e.p.stdin and not e.p.stdin.closed:
                e.p.stdin.close()
            if e.p.stdout and not e.p.stdout.closed:
                e.p.stdout.close()

    def test_no_automatic_sacrifice_reward(self):
        # Scoring a capture or a sacrifice is the searcher's job: activity is positional.
        a=attack_activity_terms(Board('6k1/8/8/3N4/8/8/8/6K1 w - - 0 1'))
        self.assertTrue(all(-150 < x < 150 for x in a))

    def test_combined_tactical_checks_and_activity(self):
        evaluate.ATTACK_ACTIVITY = True
        for fen in (SYNTHETIC[0], SYNTHETIC[1], SYNTHETIC[-2]):
            b=Board(fen); state=b.snapshot()
            s=Searcher(tt_size=1000); s.qsearch_quiet_checks=True
            best,score=s.search(b,max_depth=2,on_info=None)
            self.assertIn(best,b.legal_moves())
            self.assertEqual(b.snapshot(),state)

    def test_search_state_and_uci_option(self):
        text=io.StringIO();engine=UCIEngine(out=text)
        engine.handle('uci')
        self.assertIn('option name AttackActivity type check default false',text.getvalue())
        engine.searcher.tt.store(123,1,0,10,None)
        engine.handle('setoption name AttackActivity value false')
        self.assertFalse(evaluate.ATTACK_ACTIVITY)
        engine.handle('setoption name AttackActivity value true')
        self.assertTrue(evaluate.ATTACK_ACTIVITY)
        self.assertEqual(len(engine.searcher.tt),0)
        engine.handle('setoption name AttackActivity value false')
        self.assertFalse(evaluate.ATTACK_ACTIVITY)
        b=Board(SYNTHETIC[0]); snap=b.snapshot()
        move,sc=Searcher(tt_size=1000).search(b,max_depth=2,on_info=None)
        self.assertIn(move,b.legal_moves())
        self.assertEqual(b.snapshot(),snap)


if __name__ == '__main__':
    unittest.main(verbosity=2)
