import unittest
import threading
from unittest.mock import patch

from analysis_server import AnalysisSession
from board import Board
from notation import san_for_move
from search import EXACT, INF, MATE, Searcher, TimeUp


class SelectiveCorrectnessTests(unittest.TestCase):
    def test_equal_rooks_and_xray_use_both_legal_replies(self):
        board = Board('1k4n1/R1R4r/5p2/4p3/1Pp5/2P1P1P1/4NKbP/1N6 b - - 2 28')
        before = board.snapshot()
        move = board.parse_uci('g2b7')
        self.assertEqual(board.see_estimate(move), 0)
        self.assertEqual(board.see(move), -330)
        self.assertEqual(board.snapshot(), before)

    def test_pinned_pawn_cannot_recapture(self):
        board = Board('4k3/4p3/3p4/2B5/8/8/8/4R1K1 w - - 0 1')
        move = board.parse_uci('c5d6')
        self.assertLess(board.see_estimate(move), 0)
        self.assertEqual(board.see(move), 100)

    def test_recapture_on_last_rank_can_promote(self):
        board = Board('4k3/8/8/8/8/8/3p4/R3n1K1 w - - 0 1')
        self.assertEqual(board.see(board.parse_uci('a1e1')), 320 - 500 - 800)

    def test_selective_qsearch_delta_cannot_hide_mate_by_capture(self):
        board = Board('7k/6pp/8/7N/8/8/8/6QK w - - 0 1')
        before = board.snapshot()
        searcher = Searcher()
        searcher.selective = True
        self.assertEqual(searcher.quiesce(board, 2000, 4000, 0), MATE - 1)
        self.assertEqual(board.snapshot(), before)

    def test_sacrifice_context_ignores_unprotected_tt_score(self):
        board = Board('4r1k1/8/8/8/8/8/8/R3K2R w - - 0 1')
        searcher = Searcher()
        searcher.selective = True
        searcher.tt.store(board.hash, 14, EXACT, 5000, board.legal_moves()[0])
        self.assertNotEqual(searcher.negamax(board, 1, -100, -99, 1), 5000)

    def test_synthetic_probe_isolates_tt_and_restores_state(self):
        class StopInsideProbe(Searcher):
            def negamax(self, board, *args, **kwargs):
                self.assert_synthetic(board)
                board.make_move(board.legal_moves()[0])
                raise TimeUp

            def assert_synthetic(self, board):
                assert self._after_null and board.hash == board.compute_hash()

        board = Board()
        before = board.snapshot()
        searcher = StopInsideProbe()
        searcher.selective = True
        searcher._gain[2] = 330
        with self.assertRaises(TimeUp):
            searcher._search_after_null(board, 5, 100, 1, None, reduction=4)
        self.assertFalse(searcher._after_null)
        self.assertEqual(searcher._gain[2], 330)
        self.assertEqual(board.snapshot(), before)

    def test_settings_change_clears_previous_position_score(self):
        session = AnalysisSession(threading.Lock(), san_for_move=san_for_move, background=False)
        limits = {'min_depth': 2, 'max_depth': 2, 'seconds': 5, 'multipv': 3}
        before = session.start(limits)
        self.assertTrue(before['game_scores'])
        with patch.object(session, '_worker'):
            after = session.start({**limits, 'options': {'selective': True}})
        self.assertGreater(after['epoch'], before['epoch'])
        self.assertIsNone(after['completed'])
        self.assertEqual(after['iterations'], [])
        self.assertEqual(after['game_scores'], [])


if __name__ == '__main__':
    unittest.main()
