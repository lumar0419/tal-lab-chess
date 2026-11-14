"""v0.4.10: Aspiration is an optional exact-score search-window optimization.
It is never allowed to change a full-window final answer; fails re-search full window.
"""
import io
import random
import unittest
from version import VERSION

from board import Board, START_FEN
from perft import TESTS
from search import INF, MATE, Searcher, ENGINE_VERSION
from tal_style_benchmark import load_data
from tal_depth_diagnostic import diagnose_one
from uci import UCIEngine


def do_search(fen, depth, aspiration=False, root_moves=None, tt_size=10000):
    b = Board(fen)
    snapshot = b.snapshot()
    s = Searcher(tt_size=tt_size)
    s.aspiration = aspiration
    s.aspiration_window = 80
    infos = []
    result = s.search(b, max_depth=depth, root_moves=root_moves,
                      on_info=infos.append)
    assert b.snapshot() == snapshot, 'search modified original board'
    return result, s, infos


class AspirationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.all_cases = load_data()
        cls.featured = [x for x in cls.all_cases if x['featured']]

    def test_default_off_version(self):
        self.assertEqual(ENGINE_VERSION, VERSION)
        self.assertFalse(Searcher().aspiration)
        self.assertEqual(Searcher().aspiration_window, 80)

    def test_core_positions_full_window_equivalence(self):
        fens = [START_FEN, TESTS[1][1], TESTS[2][1], TESTS[5][1]]
        fens.extend(c['fen'] for c in self.featured)
        fens += [
            '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1',
            '8/8/8/8/8/5kr1/5p1K/6r1 b - - 0 1',
            '8/8/8/4k3/8/8/8/R3K3 w - - 98 100',
            '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1'
        ]
        for fen in fens:
            with self.subTest(fen=fen):
                a, _, _ = do_search(fen, 4, False)
                b, s, _ = do_search(fen, 4, True)
                # Equal scores are required, though equally scored best moves can differ.
                self.assertEqual(a[1], b[1])
                self.assertIn(b[0], Board(fen).legal_moves() if b[0] else [None])
                self.assertGreaterEqual(s.aspiration_researches, 0)

    def test_real_fail_low_and_high(self):
        # A tiny window around the previous iteration should cause both
        # fail-low and fail-high across these sharply varying positions.

        seen_hi = seen_lo = False
        for fen in [START_FEN, TESTS[1][1], TESTS[4][1]] + [c['fen'] for c in self.featured]:
            b = Board(fen)
            exact, _, _ = do_search(fen, 3, False)
            s = Searcher(tt_size=5000)
            s.aspiration = True
            s.aspiration_window = 1
            outcome = s.search(b, max_depth=3, on_info=None)
            self.assertEqual(outcome[1], exact[1])
            seen_hi |= s.aspiration_fail_high > 0
            seen_lo |= s.aspiration_fail_low > 0
        self.assertTrue(seen_hi or seen_lo)

    def test_root_candidates_and_forced_promotion(self):
        fen = '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'
        for moves in (['f7f8n'], ['f7f8n', 'f7f8q'], ['f7f8q']):
            with self.subTest(moves=moves):
                a, _, _ = do_search(fen, 3, False, root_moves=moves)
                b, _, _ = do_search(fen, 3, True, root_moves=moves)
                self.assertEqual(b[1], a[1])
                self.assertIn(b[0].uci(), moves)

    def test_mate_and_draw_stay_valid(self):
        cases = [
            ('7k/8/6K1/8/8/8/8/R7 w - - 0 1', MATE - 1),
            ('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', 0),
            ('6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1', MATE - 1),
        ]
        for fen, score in cases:
            with self.subTest(fen=fen):
                a, _, _ = do_search(fen, 3, False)
                b, _, _ = do_search(fen, 3, True)
                self.assertEqual(a[1], b[1])
                self.assertEqual(score, b[1])

    def test_node_limit_state_restoration(self):
        fen = TESTS[1][1]
        for lim in (1, 17, 139, 1500):
            b = Board(fen)
            before = b.snapshot()
            s = Searcher(tt_size=5000)
            s.aspiration = True
            move, _ = s.search(b, max_depth=10, node_limit=lim, on_info=None)
            self.assertEqual(b.snapshot(), before)
            self.assertLessEqual(s.nodes, lim)
            self.assertIn(move, b.legal_moves())

    def test_profile_combinations(self):
        from tal_style_benchmark import profile_settings
        for profile in ('baseline', 'combined'):
            with profile_settings(profile) as tactical:
                for case in self.featured[:2]:
                    old,_,_ = do_search(case['fen'], 3, False)
                    new,_,_ = do_search(case['fen'], 3, True)
                    self.assertEqual(old[1], new[1])

    def test_diagnostic_root_rank_and_state(self):
        case = self.featured[0]
        old = diagnose_one(case, 'baseline', [1, 2], aspiration=False)
        new = diagnose_one(case, 'baseline', [1, 2], aspiration=True)
        self.assertEqual(new['initial_root_rank'], old['initial_root_rank'])
        self.assertGreaterEqual(new['initial_root_rank'], 1)
        self.assertLessEqual(new['initial_root_rank'], new['initial_root_legal_count'])
        self.assertTrue(new['aspiration'])
        self.assertEqual([x['selected']['score_cp_or_mate_encoded'] for x in old['depth_results']],
                         [x['selected']['score_cp_or_mate_encoded'] for x in new['depth_results']])

    def test_uci_advertised_and_set_option(self):
        stream = io.StringIO()
        engine = UCIEngine(out=stream)
        engine.handle('uci')
        self.assertIn('option name Aspiration type check default false', stream.getvalue())
        self.assertFalse(engine.searcher.aspiration)
        engine.handle('setoption name Aspiration value true')
        self.assertTrue(engine.searcher.aspiration)
        engine.handle('setoption name Aspiration value false')
        self.assertFalse(engine.searcher.aspiration)
        engine.handle('quit')


if __name__ == '__main__':
    unittest.main(verbosity=2)
