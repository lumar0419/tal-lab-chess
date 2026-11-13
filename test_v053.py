"""v0.5.3 regression: history-aware TT carryover, conservative LMR, legal master scores."""
import time
import unittest

from board import Board
from search import Searcher, MATE
from master_sacrifices import build_cases, replay_san, verify_dataset, GAMES
from web_server import Game


class HistoricalGames(unittest.TestCase):
    def test_full_san_replay_and_archived_fens(self):
        cases = verify_dataset()
        self.assertEqual(len(cases), 6)
        self.assertEqual(len(set(c['id'] for c in cases)), 6)
        self.assertEqual({c['master'] for c in cases},
                         {'Bobby Fischer', 'Garry Kasparov', 'Adolf Anderssen'})
        for game in GAMES:
            positions = replay_san(game)
            self.assertGreater(len(positions), max(c['ply'] for c in game['cases']))

    def test_legal_historical_moves_and_restored_state(self):
        for case in verify_dataset():
            b = Board(case['fen'])
            original = b.snapshot()
            m = b.parse_uci(case['historical_uci'])
            self.assertIsNotNone(m, case['id'])
            b.make_move(m)
            b.unmake_move()
            self.assertEqual(b.snapshot(), original)


class SearchTests(unittest.TestCase):
    def test_lmr_opt_in_default_off(self):
        s = Searcher(tt_size=200)
        self.assertFalse(s.lmr)
        self.assertEqual(s.lmr_probes, 0)

    def test_lmr_tactical_cases_are_legal(self):
        # LMR never drops moves, and forced mates/promotion tactics stay intact.
        cases = [
            ('7k/8/6K1/8/8/8/8/R7 w - - 0 1', 2),
            ('6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1', 2),
            ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', 3),
        ]
        for fen, depth in cases:
            b = Board(fen)
            original = b.snapshot()
            for enabled in (False, True):
                s = Searcher(tt_size=2_000)
                s.lmr = enabled
                chosen, score = s.search(b, max_depth=depth)
                self.assertEqual(b.snapshot(), original)
                self.assertIn(chosen, b.legal_moves())
                if '7k/8/6K1' in fen:
                    self.assertEqual(score, MATE-1)

    def test_lmr_reduction_is_reachable(self):
        # Bound probe must reach a late nonchecking quiet move after several moves.
        s = Searcher(tt_size=6_000)
        s.lmr = True
        b = Board()
        s.search(b, max_depth=5, on_info=lambda info: None)
        self.assertGreater(s.lmr_probes, 0)

    def test_repeated_search_state_and_legal_move(self):
        b = Board()
        s = Searcher(tt_size=20_000)
        first, _ = s.search(b, max_depth=3)
        gen = s.tt.generation
        b.make_move(first)
        second, _ = s.search(b, max_depth=2)
        self.assertIn(second, b.legal_moves())
        self.assertEqual(s.tt.generation, gen + 1)


class WebTTTests(unittest.TestCase):
    def _wait(self, game, limit=8):
        end = time.monotonic() + limit
        while game.state()['thinking'] and time.monotonic() < end:
            time.sleep(.025)
        self.assertFalse(game.state()['thinking'])
        self.assertIsNone(game.state()['error'])

    def test_tt_reused_within_one_game_but_reset_on_new(self):
        game = Game()
        game.new({'side': 'black', 'depth': 2, 'seconds': .3})
        self._wait(game)
        first = game._cached_searcher
        self.assertIsNotNone(first)
        self.assertGreater(len(first.tt), 0)
        self.assertEqual(first.tt.generation, 1)
        legal = game.state()['legal'][0]
        game.move(legal)
        self._wait(game)
        self.assertIs(game._cached_searcher, first)
        self.assertEqual(first.tt.generation, 2)
        game.new({'side': 'white', 'depth': 1, 'seconds': .1})
        self.assertIsNone(game._cached_searcher)


if __name__ == '__main__':
    unittest.main(verbosity=2)
