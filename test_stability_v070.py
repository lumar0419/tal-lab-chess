import threading
import unittest

from analysis_server import AnalysisSession
from board import Board
from notation import san_for_move
from search import Searcher, MATE


class StabilityTests(unittest.TestCase):
    def test_mate_pv_is_replayed_with_and_without_tt(self):
        fen = 'r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22'
        for size in (0, 2, 60000):
            searcher = Searcher(size)
            groups = []
            board = Board(fen)
            before = board.snapshot()
            searcher.search(board, max_depth=3, multipv=3, on_info=None,
                            on_multipv=groups.append)
            self.assertEqual(board.snapshot(), before)
            line = groups[-1][0]
            self.assertEqual(line.score, MATE - 3)
            self.assertEqual(len(line.pv), 3)
            for move in line.pv:
                self.assertIn(move, board.legal_moves())
                board.make_move(move)
            self.assertEqual(board.outcome()[0], '1-0')
            self.assertTrue(board.in_check())

    def test_same_fen_reload_and_stop_invalidate_delayed_start(self):
        session = AnalysisSession(threading.Lock(), background=False)
        for change in (session.reset, session.stop):
            before = session.state()
            change()
            result = session.start({'expected_fen': before['fen'],
                                    'expected_epoch': before['epoch']}, mode='restart')
            self.assertEqual(result['status'], 'idle')
            self.assertGreater(result['epoch'], before['epoch'])
            self.assertIsNone(result['completed'])

    def test_cancel_before_first_node(self):
        seen = []
        searcher = Searcher()
        board = Board()
        before = board.snapshot()
        move, _ = searcher.search(board, max_depth=3, multipv=3, on_info=None,
                                 on_multipv=seen.append, cancel_check=lambda: True)
        self.assertIn(move, board.legal_moves())
        self.assertEqual(board.snapshot(), before)
        self.assertEqual(searcher.nodes, 0)
        self.assertEqual(seen, [])

    def test_black_scores_graph_and_sync_threaded_agree(self):
        settings = {'min_depth': 2, 'max_depth': 2, 'multipv': 3, 'seconds': 5}
        sessions = [AnalysisSession(threading.Lock(), san_for_move=san_for_move, background=mode)
                    for mode in (False, True)]
        outputs = []
        for session in sessions:
            session.move('e2e4')
            finished = threading.Event()
            def update(state):
                if state['completed']['depth'] == 2:
                    finished.set()
            session.on_update = update
            session.start(settings)
            self.assertTrue(finished.wait(5))
            result = session.state()
            candidates = result['completed']['candidates']
            self.assertEqual([x['score'] for x in candidates],
                             sorted(x['score'] for x in candidates))
            self.assertEqual(result['game_scores'][0]['score'], candidates[0]['score'])
            self.assertEqual(result['completed']['nodes'], max(x['nodes'] for x in candidates))
            outputs.append([(x['score'], x['pv'], x['pv_san']) for x in candidates])
        self.assertEqual(*outputs)
