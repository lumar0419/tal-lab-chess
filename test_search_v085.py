import unittest

from board import Board
from search import INF, MATE, Searcher, TimeUp


class HorizonRuleTests(unittest.TestCase):
    def test_fifty_move_claim_available_via_quiet_defense_at_horizon(self):
        for color, fen in (
            ('white', '7k/8/8/8/8/8/r7/6K1 w - - 99 50'),
            ('black', '6k1/R7/8/8/8/8/8/7K b - - 99 50'),
        ):
            with self.subTest(color=color):
                board = Board(fen)
                snapshot = board.snapshot()
                search = Searcher()
                self.assertEqual(search.quiesce(board, -INF, INF, 1), 0)
                self.assertGreater(search.draw_hits, 0)
                self.assertEqual(board.snapshot(), snapshot)
                self.assertEqual(board.hash, board.compute_hash())
                earlier = Board(fen.replace(' 99 ', ' 98 '))
                self.assertLess(Searcher().quiesce(earlier, -INF, INF, 1), 0)

    def test_announced_threefold_at_horizon_and_history_isolation(self):
        board = Board('7k/4q3/8/8/8/8/8/R5K1 b - - 0 1')
        for move in 'h8g8 g1h1 g8h8 h1g1 h8g8 g1h1 g8h8'.split():
            board.push_uci(move)
        self.assertEqual(board.repetition_count(), 2)
        snapshot = board.snapshot()
        search = Searcher()
        search.root_len = len(board.history)
        self.assertEqual(search.quiesce(board, -INF, INF, 1), 0)
        self.assertGreater(search.draw_hits, 0)
        self.assertLess(Searcher().quiesce(Board(board.fen()), -INF, INF, 1), 0)
        self.assertEqual(board.snapshot(), snapshot)

    def test_mate_on_move_50_outranks_claim(self):
        board = Board('7k/8/6K1/8/8/8/8/R7 w - - 99 50')
        search = Searcher()
        search.qsearch_quiet_checks = True
        search.qsearch_forcing_replies = 2
        self.assertEqual(search.quiesce(board, -INF, INF, 1), MATE - 2)

    def test_check_filter_limits_own_candidates_but_not_evasions(self):
        board = Board('b2r3r/k4p1p/p2q1np1/Np1P4/3p1Q2/P4PPB/1PP4P/1K2R3 w - - 0 25')
        board.push_uci('e1e7')
        self.assertEqual(len(board.legal_moves()), 8)
        snapshot = board.snapshot()
        normal = Searcher()
        filtered = Searcher()
        filtered.qsearch_forcing_replies = 2
        self.assertTrue(filtered._too_many_evasions(board))
        self.assertEqual(filtered.quiesce(board, -INF, INF, 0),
                         normal.quiesce(board, -INF, INF, 0))
        self.assertEqual(board.snapshot(), snapshot)

    def test_interrupted_quiet_check_search_restores_hash_and_history(self):
        board = Board('7k/8/6K1/8/8/8/8/R7 w - - 0 1')
        snapshot = board.snapshot()
        search = Searcher()
        search.qsearch_quiet_checks = True
        search.qsearch_forcing_replies = 2
        search.node_limit = search._next_check = 2
        with self.assertRaises(TimeUp):
            search.quiesce(board, -INF, INF, 0)
        self.assertEqual(board.snapshot(), snapshot)
        self.assertEqual(board.hash, board.compute_hash())
