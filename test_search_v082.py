import unittest

from board import Board
from search import INF, MATE, MAX_PLY, Searcher, TimeUp


class SearchBoundaryTests(unittest.TestCase):
    def test_cancel_from_iteration_keeps_previous_complete_group(self):
        for count in (1, 3):
            b = Board()
            before = b.snapshot()
            groups = []

            def cancel(depth):
                if depth == 2:
                    raise TimeUp()

            best, score = Searcher().search(
                b, max_depth=4, multipv=count, on_iteration=cancel,
                on_info=(lambda info: groups.append([info])) if count == 1 else None,
                on_multipv=groups.append if count > 1 else None)
            self.assertEqual(b.snapshot(), before)
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]), count)
            self.assertEqual((best, score), (groups[0][0].pv[0], groups[0][0].score))

    def test_ply_limit_retains_checkmate_and_stalemate(self):
        for fen, expected in (
            ('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1', -MATE + MAX_PLY),
            ('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', 0),
        ):
            with self.subTest(fen=fen):
                board = Board(fen)
                self.assertEqual(Searcher().negamax(board, 1, -INF, INF, MAX_PLY), expected)
                self.assertEqual(Searcher().quiesce(board, -INF, INF, MAX_PLY), expected)

    def test_evasion_generator_preserves_legal_order(self):
        fens = [
            '4r1k1/8/8/8/8/8/3B4/4K3 w - - 0 1',
            '4r1k1/8/8/8/1b6/8/8/4K3 w - - 0 1',
            '8/8/8/3pP3/4K3/8/k7/8 w - d6 0 1',
            'K6r/1P6/8/8/8/8/8/7k w - - 0 1',
        ]
        for fen in fens:
            with self.subTest(fen=fen):
                b = Board(fen)
                self.assertTrue(b.in_check())
                actual = []
                for move in b.evasion_candidates():
                    b.make_move(move)
                    if not b.in_check(b.side ^ 1):
                        actual.append(move)
                    b.unmake_move()
                self.assertEqual(actual, b.legal_moves())
