"""Independent coverage of quiet-check geometry and the capture continuation."""
import random
import unittest

import chess

from board import Board
from search import INF, MATE, MAX_PLY, Searcher


class QuietChecksTests(unittest.TestCase):
    def test_generated_checks_match_legal_oracle_in_original_order(self):
        rng = random.Random(83)
        samples = [
            chess.Board('5k2/8/8/8/8/8/8/4K2R w K - 0 1'),
            chess.Board('4k3/8/8/8/8/8/4B3/4R1K1 w - - 0 1'),
            chess.Board('8/5P1k/5K2/8/8/8/8/8 w - - 0 1'),
        ]
        for _ in range(16):
            position = chess.Board()
            for _ in range(84):
                moves = list(position.legal_moves)
                if not moves:
                    break
                position.push(rng.choice(moves))
                samples.append(position.copy(stack=False))
        seen = 0
        for sample in samples:
            b = Board(sample.fen(en_passant='fen'))
            snapshot = b.snapshot()
            oracle = {m.uci() for m in sample.legal_moves
                      if not m.promotion and not sample.is_capture(m) and sample.gives_check(m)}
            candidates = [m.uci() for m in b.quiet_check_candidates()]
            actual = [m for m in candidates if m in oracle]
            normal = [m.uci() for m in b.pseudo_legal_moves() if m.uci() in oracle]
            self.assertEqual(set(actual), oracle, sample.fen())
            self.assertEqual(actual, normal, sample.fen())
            self.assertEqual(snapshot, b.snapshot())
            seen += len(actual)
        self.assertGreater(seen, 250)

    def test_capture_bridge_requires_check_budget_and_finds_followup(self):
        b = Board('7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1')
        before = b.snapshot()
        search = Searcher(tt_size=0)
        search.qsearch_capture_bridge = True
        default = search.quiesce(b, -INF, INF, 0)
        search.qsearch_capture_bridge = False
        self.assertEqual(default, search.quiesce(b, -INF, INF, 0))

        search.pv_table = [()] * (MAX_PLY + 2)
        search.qsearch_quiet_checks = search.check_continuation = True
        before_bridge = search.quiesce(b, -INF, INF, 0)
        self.assertEqual(search.pv_table[0][0].uci(), 'g2f1')
        search.qsearch_capture_bridge = True
        with_bridge = search.quiesce(b, -INF, INF, 0)
        self.assertLess(with_bridge, before_bridge)
        self.assertFalse(search.pv_table[0])  # Stand pat beats the offered queen.
        b.push_uci('g2f1')
        self.assertEqual(search.quiesce(b, -INF, INF, 0), MATE - 1)
        b.unmake_move()
        self.assertEqual(b.snapshot(), before)
