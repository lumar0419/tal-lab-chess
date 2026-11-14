import unittest

from board import Board
from search import INF, MATE, Searcher, TimeUp


class ExperimentalSearchTests(unittest.TestCase):
    def test_null_pass_clears_ep_and_restores_exact_state(self):
        board = Board()
        for move in ('e2e4', 'a7a6', 'e4e5', 'd7d5'):
            board.push_uci(move)
        self.assertNotEqual(board.ep_key, 0)
        original = board.snapshot()
        state = board.make_null_move()
        self.assertEqual(board.ep, 0)
        self.assertEqual(board.hash, board.compute_hash())
        self.assertEqual(board.halfmove, 0)
        self.assertEqual(len(board.history), len(original[-1]))
        board.unmake_null_move(state)
        self.assertEqual(board.snapshot(), original)

    def test_interrupted_probe_unwinds_moves_before_restoring_pass(self):
        class InterruptedProbe(Searcher):
            def negamax(self, board, *args, **kwargs):
                board.make_move(board.legal_moves()[0])
                board.make_move(board.legal_moves()[0])
                self.draw_hits += 1
                raise TimeUp

        board = Board()
        original = board.snapshot()
        searcher = InterruptedProbe()
        with self.assertRaises(TimeUp):
            searcher._search_after_null(board, 4, 10, 2, 1)
        self.assertEqual(board.snapshot(), original)
        self.assertFalse(searcher._after_null)
        self.assertEqual(searcher.draw_hits, 0)
        self.assertEqual(len(searcher.tt), 0)

    def test_null_probe_does_not_write_tt_or_ordering(self):
        board = Board()
        searcher = Searcher(tt_size=200)
        searcher._search_after_null(board, 4, 10, 1, None)
        self.assertEqual(len(searcher.tt), 0)
        self.assertFalse(searcher.history)
        self.assertEqual(searcher.null_probes, 1)

    def test_null_skips_pawn_endgame_checked_node_and_draw_boundary(self):
        for fen in ('8/8/8/8/8/2k5/4p3/4K3 w - - 0 1',
                    '4r1k1/8/8/8/8/8/8/R3K2R w - - 0 1',
                    'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 98 50'):
            with self.subTest(fen=fen):
                searcher = Searcher(tt_size=0)
                searcher.null_move_pruning = True
                searcher.null_threat_extension = True
                searcher.negamax(Board(fen), 3, -10001, -10000, 1)
                self.assertEqual(searcher.null_probes, 0)

    def test_zero_check_budget_still_computes_mate_and_evasions(self):
        searcher = Searcher(tt_size=0)
        mate = Board('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1')
        checked = Board('4r1k1/8/8/8/8/8/8/R3K3 w - - 0 1')
        self.assertEqual(searcher.negamax(mate, 0, -INF, INF, 1, checks_left=0), -MATE + 1)
        self.assertEqual(searcher.negamax(checked, 0, -INF, INF, 1, checks_left=0),
                         searcher.quiesce(checked, -INF, INF, 1))

    def test_check_budget_separates_transposition_scores(self):
        board = Board('4r1k1/8/8/8/8/8/8/R3K2R w - - 0 1')
        searcher = Searcher(tt_size=200)
        searcher.negamax(board, 1, -INF, INF, 1, checks_left=0)
        self.assertIsNone(searcher.tt.get(board.hash))
        searcher.negamax(board, 1, -INF, INF, 1)
        self.assertIsNotNone(searcher.tt.get(board.hash))

    def test_threat_probe_uses_mate_window_instead_of_original_cp_window(self):
        board = Board('7k/8/6K1/8/8/n7/6b1/R4Q2 b - - 0 1')
        searcher = Searcher(tt_size=0)
        searcher.null_threat_extension = True
        self.assertGreater(searcher.negamax(board, 4, -2, -1, 1), -MATE + 1000)
        self.assertEqual(searcher.null_threats, 1)


if __name__ == '__main__':
    unittest.main()
