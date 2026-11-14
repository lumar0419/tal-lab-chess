"""v0.4.11: non-destructive attacking move ordering + bounded qsearch checking continuation.

Use: python -m unittest -v test_tactical_ordering.py
Does not require Stockfish or python-chess.
"""
import io
import random
import unittest
from version import VERSION

from board import Board, START_FEN
from perft import TESTS
from search import ENGINE_VERSION, INF, MATE, Searcher
from tal_style_benchmark import load_data
from uci import UCIEngine


def run(fen, depth=3, ordering=False, continuation=False, tactical=False,
        root_moves=None, node_limit=None):
    b = Board(fen)
    original = b.snapshot()
    s = Searcher(tt_size=25000)
    s.tactical_ordering = ordering
    s.check_continuation = continuation
    s.qsearch_quiet_checks = tactical
    m, score = s.search(b, max_depth=depth, on_info=None,
                        root_moves=root_moves, node_limit=node_limit)
    assert b.snapshot() == original, 'Board was modified by search'
    assert m is None or m in b.legal_moves(), 'Search returned illegal move'
    return (m.uci() if m else None), score, s


class TacticalOrderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cases = load_data()
        cls.featured = [c for c in cases if c.get('featured')]

    def test_version_defaults(self):
        s = Searcher()
        self.assertEqual(ENGINE_VERSION, VERSION)
        self.assertFalse(s.tactical_ordering)
        self.assertFalse(s.check_continuation)
        self.assertFalse(s.qsearch_quiet_checks)
        self.assertTrue(s.pvs)

    def test_ordering_permutation_never_drops_moves(self):
        fens = [START_FEN] + [x[1] for x in TESTS] + [c['fen'] for c in self.featured]
        for fen in fens:
            with self.subTest(fen=fen):
                b = Board(fen)
                original = b.snapshot()
                moves = b.pseudo_legal_moves()
                s = Searcher()
                checks = set(s._quiet_check_candidates(b, moves=moves))
                self.assertTrue(checks.issubset(set(moves)))
                self.assertEqual(len(moves), len(set(moves)))
                after = s.order_moves(b, list(moves), None, 0, checks)
                self.assertEqual(set(after), set(moves))
                self.assertEqual(len(after), len(moves))
                self.assertEqual(b.snapshot(), original)

    def test_initial_tal_ranks_are_reported_not_forced(self):
        # This is *only* initial ordering without a TT/history, not tactical soundness.
        results = []
        for case in self.featured:
            b = Board(case['fen'])
            ref = case['tal_move']
            s = Searcher()
            original = [m.uci() for m in s.order_moves(b, b.pseudo_legal_moves(), None, 0)]
            moves = b.pseudo_legal_moves()
            checks = set(s._quiet_check_candidates(b, moves=moves))
            ordered = [m.uci() for m in s.order_moves(b, moves, None, 0, checks)]
            self.assertEqual(set(original), set(ordered))
            self.assertIn(ref, ordered)
            results.append((ref, original.index(ref) + 1, ordered.index(ref) + 1))
        # Tal examples guide diagnostics, not the engine's final selection.
        self.assertEqual(len(results), 4)
        self.assertTrue(any(new < old for _, old, new in results), results)

    def test_fixed_depth_search_same_exact_scores(self):
        fens = [START_FEN, TESTS[2][1]] + [c['fen'] for c in self.featured]
        for fen in fens:
            with self.subTest(fen=fen):
                _, oldscore, _ = run(fen, depth=3, ordering=False)
                _, newscore, s = run(fen, depth=3, ordering=True)
                self.assertEqual(oldscore, newscore)
                self.assertGreaterEqual(s.tactical_order_nodes, 1)

    def test_promotions_mates_and_stalemate(self):
        samples = [
            ('6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1', MATE - 1, 'f7f8n'),
            ('7k/8/6K1/8/8/8/8/R7 w - - 0 1', MATE - 1, 'a1a8'),
            ('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', 0, None),
        ]
        for fen, expected, best in samples:
            with self.subTest(fen=fen):
                move, score, _ = run(fen, depth=3, ordering=True)
                self.assertEqual(score, expected)
                self.assertEqual(move, best)

    def test_searchmoves_and_node_limit(self):
        fen = '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'
        for candidates in (['f7f8q'], ['f7f8n'], ['f7f8n', 'f7f8q']):
            with self.subTest(candidates=candidates):
                move, score, _ = run(fen, 3, ordering=True, root_moves=candidates)
                self.assertIn(move, candidates)
        for lim in (1, 7, 83, 751):
            move, score, s = run(START_FEN, 12, ordering=True, node_limit=lim)
            self.assertLessEqual(s.nodes, lim)
            self.assertIsNotNone(move)

    def test_continuation_without_tactical_checks_is_inert(self):
        fens = [START_FEN, self.featured[0]['fen'], '7k/8/6K1/8/8/8/8/R7 w - - 0 1']
        for fen in fens:
            a = run(fen, 3, continuation=False, tactical=False)
            b = run(fen, 3, continuation=True, tactical=False)
            self.assertEqual(a[:2], b[:2])
            self.assertEqual(b[2].check_continuation_nodes, 0)

    def test_continuation_finds_quiet_mate_and_restores_board(self):
        fen = '7k/8/6K1/8/8/8/8/R7 w - - 0 1'
        for following in (False, True):
            b = Board(fen)
            before = b.snapshot()
            s = Searcher()
            s.qsearch_quiet_checks = True
            s.check_continuation = following
            score = s.quiesce(b, -INF, INF, 0)
            self.assertEqual(score, MATE - 1)
            self.assertEqual(b.snapshot(), before)
        # The second checking opportunity is actually reached at least once.
        s = run(self.featured[0]['fen'], 3, continuation=True, tactical=True)[2]
        self.assertGreater(s.check_continuation_nodes, 0)

    def test_stopping_with_both_experimental_options(self):
        for fen in (START_FEN, self.featured[0]['fen']):
            for limit in (50, 600):
                _, _, s = run(fen, depth=30, ordering=True, tactical=True,
                              continuation=True, node_limit=limit)
                self.assertLessEqual(s.nodes, limit)

    def test_uci_options_and_clear_tt(self):
        sink = io.StringIO()
        e = UCIEngine(out=sink)
        e.handle('uci')
        self.assertIn('option name TacticalOrdering type check default false', sink.getvalue())
        self.assertIn('option name CheckContinuation type check default false', sink.getvalue())
        for setting, attr in (('TacticalOrdering', 'tactical_ordering'),
                              ('CheckContinuation', 'check_continuation')):
            e.searcher.tt.store(123, 1, 0, 42, None)
            self.assertGreater(len(e.searcher.tt), 0)
            e.handle(f'setoption name {setting} value true')
            self.assertEqual(len(e.searcher.tt), 0)
            self.assertTrue(getattr(e.searcher, attr))
            e.handle(f'setoption name {setting} value false')
            self.assertFalse(getattr(e.searcher, attr))
        e.handle('quit')

    def test_real_uci_process_with_tal_options(self):
        from test_uci import Engine
        fen = '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'
        e = Engine()
        try:
            e.send('uci')
            line, _, _ = e.wait_for(lambda s: s == 'uciok', 5)
            self.assertEqual(line, 'uciok')
            e.send('setoption name TacticalOrdering value true')
            e.send('setoption name TacticalChecks value true')
            e.send('setoption name CheckContinuation value true')
            e.send('position fen '+fen)
            e.send('go depth 3')
            best, info, _ = e.bestmove(10)
            self.assertEqual(best, 'f7f8n')
            self.assertFalse(any('search error' in x for x in info))
        finally:
            e.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
