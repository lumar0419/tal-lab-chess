import threading
import time
import unittest
from unittest.mock import patch

from analysis_server import AnalysisSession
from board import Board
from deep_analysis import analyze_deep
from notation import san_for_move
from search import EXACT, LOWER, MOVE_ONLY, TranspositionTable
from search_gate import AUTO, DEEP, GAME, SearchGate


LASKER = 'r4rk1/1b2bppp/ppq1p3/2ppB2n/5P2/1P1BP3/P1PPQ1PP/R4RK1 w - - 0 15'
ANDERSSEN = 'r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22'
QUEEN_OFFER = '7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1'


class DeepWorkflowTests(unittest.TestCase):
    def test_mate_discovery_and_board_restore(self):
        board = Board(ANDERSSEN)
        before = board.snapshot()
        report = analyze_deep(board, 4, max_depth=3, profile='full')
        self.assertEqual(report['root_move'], 'f3f6')
        self.assertEqual(report['root'][-1]['depth'], 3)
        move = report['candidates'][0]
        self.assertTrue(move['reference'])
        self.assertEqual(move['legal_replies'], 2)
        self.assertEqual(move['verification'], 'mate_proved')
        self.assertEqual(move['proof']['max_plies'], 3)
        self.assertEqual(board.snapshot(), before)

    def test_losing_offers_keep_their_negative_comparison(self):
        result = analyze_deep(Board(QUEEN_OFFER), 2, max_depth=2, candidate='e2e4')
        move = next(row for row in result['candidates'] if row['move'] == 'e2e4')
        self.assertIsNotNone(move['offer'])
        self.assertEqual(move['iterations'][-1]['pv'][0], 'e2e4')
        self.assertLess(move['comparison']['delta_for_mover'], 0)
        self.assertTrue(move['defense_accepts'])
        self.assertIsNone(move['proof'])
        self.assertEqual(move['time_limit'], result['candidates'][0]['time_limit'])

    def test_cancellation_has_no_completed_depth_or_mutation(self):
        board = Board(LASKER)
        before = board.snapshot()
        result = analyze_deep(board, 60, cancel_check=lambda: True)
        self.assertEqual(result['outcome'], 'cancelled')
        self.assertEqual(result['root'], [])
        self.assertEqual(board.snapshot(), before)

    def test_transposition_policy_keeps_deeper_score(self):
        tt = TranspositionTable(20)
        tt.preserve_deeper = True
        tt.store(3, 8, EXACT, 15, 'a')
        tt.store(3, 8, LOWER, 19, 'b')
        tt.store(3, 5, EXACT, 30, 'c')
        tt.store(3, 0, MOVE_ONLY, 0, 'd')
        self.assertEqual(tt.get(3)[:4], (8, EXACT, 15, 'a'))
        tt.store(3, 9, LOWER, 45, 'e')
        self.assertEqual(tt.get(3)[:4], (9, LOWER, 45, 'e'))


class DeepSessionTests(unittest.TestCase):
    def test_deep_is_explicit_and_fast_values_are_preserved(self):
        session = AnalysisSession(threading.Lock(), san_for_move=san_for_move, background=False)
        session.set_fen(ANDERSSEN)

        def finite(board, seconds, **kwargs):
            self.assertEqual(seconds, 600)
            return analyze_deep(board, .8, max_depth=3, **kwargs)

        with self.assertRaises(ValueError):
            session.start({'deep': True, 'seconds': 60}, mode='auto')
        with self.assertRaises(ValueError):
            session.start({'deep': True, 'seconds': 120})
        with patch('analysis_server.analyze_deep', side_effect=finite):
            result = session.start({'deep': True, 'seconds': 600,
                                    'expected_fen': ANDERSSEN})
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['seconds'], 30)
        self.assertEqual(result['multipv'], 3)
        self.assertEqual(result['completed']['pv'][0], 'f3f6')
        self.assertEqual(result['completed']['best_san'], 'Qf6+')
        self.assertEqual(len(result['completed']['candidates']), 1)
        self.assertIsNone(session.reset()['deep'])

    def test_interrupted_deep_work_releases_slot_to_auto(self):
        gate = SearchGate()
        session = AnalysisSession(gate, search_wait_seconds=1)
        started = threading.Event()
        end = threading.Event()

        def computation(board, seconds, *, cancel_check, **kwargs):
            started.set()
            end.wait(timeout=.01)
            while not cancel_check():
                end.wait(timeout=.01)

        with patch('analysis_server.analyze_deep', side_effect=computation):
            session.start({'deep': True, 'seconds': 600})
            self.assertTrue(started.wait(timeout=2))
            state = session.state()
            same_session = session.start({'expected_fen': state['fen'], 'expected_epoch': state['epoch'],
                                          'automatic': True}, mode='restart')
            self.assertEqual(same_session['epoch'], state['epoch'])
            self.assertTrue(same_session['active'])
            self.assertTrue(gate.acquire_job(AUTO, threading.Event(), lambda: False, timeout=1))
            gate.release()
            end.set()
        self.assertEqual(session.state()['status'], 'preempted')

    def test_queued_game_already_has_priority(self):
        gate = SearchGate()
        self.assertTrue(gate.acquire_job(GAME, threading.Event(), lambda: False, 0))
        self.assertFalse(gate.acquire_job(DEEP, threading.Event(), lambda: False, 0))
        gate.release()


if __name__ == '__main__':
    unittest.main()
