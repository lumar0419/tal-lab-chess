import io
import threading
import unittest
from unittest.mock import patch

from analysis_server import AnalysisSession
from board import Board
from notation import san_for_move
from sacrifice import analyze_candidate, discover_sacrifices, mate_proof
from search import Searcher, TimeUp
from uci import UCIEngine, UCISearcher


ANDERSSEN = 'r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22'
QUEEN_OFFER = '7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1'


class SacrificeUpgradeTests(unittest.TestCase):
    def test_discovery_finds_mate_and_lists_acceptance_and_decline(self):
        board = Board(ANDERSSEN)
        snapshot = board.snapshot()
        report = discover_sacrifices(board, depth=3, seconds=5)
        self.assertTrue(report['scan_complete'])
        self.assertEqual(report['ranked_moves'][0], 'f3f6')
        candidate = report['candidates'][0]
        self.assertEqual(candidate['status'], 'verified_mate_sacrifice')
        self.assertEqual(candidate['proof']['max_plies'], 3)
        self.assertEqual(candidate['legal_replies'], 2)
        self.assertEqual({line['response'] for line in candidate['defenses']}, {'accepts', 'declines'})
        self.assertEqual(board.snapshot(), snapshot)

    def test_proof_distinguishes_short_limit_and_interruption(self):
        board = Board(ANDERSSEN)
        self.assertEqual(mate_proof(board, 'f3f6', 1)['status'], 'not_forced_within_limit')
        self.assertEqual(mate_proof(board, 'f3f6', 3, node_budget=0)['status'], 'incomplete')
        self.assertEqual(mate_proof(board, 'f3f6', 3, cancel_check=lambda: True)['status'], 'incomplete')
        self.assertEqual(mate_proof(board, 'f3f6', 3)['status'], 'proved')

    def test_losing_queen_offer_does_not_report_verified_mate(self):
        result = analyze_candidate(Board(QUEEN_OFFER), 'e2e4', depth=3, seconds=3)
        self.assertEqual(result['status'], 'candidate')
        self.assertEqual(result['best_defense'], 'd5e4')
        self.assertIsNone(result['proof'])

    def test_all_captures_of_the_offered_piece_are_acceptances(self):
        board = Board('3rkb1r/p2nqppp/5n2/1B2p1B1/4P3/1Q6/PPP2PPP/2KR3R w k - 3 13')
        result = analyze_candidate(board, 'd1d7', depth=3, seconds=3)
        self.assertEqual({line['uci'] for line in result['acceptances']}, {'f6d7'})
        self.assertEqual({(line['move'], line['response']) for line in result['defenses']},
                         {('d8d7', 'accepts'), ('e7d7', 'accepts'), ('f6d7', 'accepts')})

    def test_draw_claim_stops_mate_proof(self):
        board = Board('7k/8/5K2/8/8/8/8/6R1 w - - 99 50')
        self.assertEqual(mate_proof(board, 'g1g7', 5)['status'], 'not_forced_within_limit')

    def test_discovery_session_validates_position_and_boolean(self):
        session = AnalysisSession(threading.Lock(), san_for_move=san_for_move, background=False)
        session.set_fen(ANDERSSEN)
        with self.assertRaises(ValueError):
            session.sacrifice({'expected_fen': ANDERSSEN, 'discover': 'true'})
        with self.assertRaises(ValueError):
            session.sacrifice({'expected_fen': QUEEN_OFFER, 'discover': True})
        report = session.sacrifice({'expected_fen': ANDERSSEN, 'discover': True})
        self.assertEqual(report['fen'], ANDERSSEN)
        self.assertIn('f3f6', report['ranked_moves'])


class ProtocolUpgradeTests(unittest.TestCase):
    def test_uci_reports_completed_ranked_multipv(self):
        output = io.StringIO()
        engine = UCIEngine(output)
        engine.handle('uci')
        engine.handle('setoption name MultiPV value 3')
        engine.handle('position startpos')
        engine.handle('go depth 3 searchmoves e2e4 d2d4 g1f3')
        engine.thread.join(timeout=10)
        self.assertFalse(engine.thread.is_alive())
        lines = output.getvalue().splitlines()
        self.assertIn('option name MultiPV type spin default 1 min 1 max 5', lines)
        group = [line.split() for line in lines if line.startswith('info depth 3 multipv')]
        self.assertEqual([line[4] for line in group], ['1', '2', '3'])
        first_moves = [line[line.index('pv') + 1] for line in group]
        self.assertEqual(set(first_moves), {'e2e4', 'd2d4', 'g1f3'})
        self.assertEqual(lines[-1].split()[1], first_moves[0])

    def test_expired_ponder_budget_is_not_extended_to_poll_time(self):
        searcher = UCISearcher(tt_size=0)
        searcher.pending_time = 10.0, 0.05
        with patch('search.time.monotonic', return_value=10.08):
            with self.assertRaises(TimeUp):
                searcher._check_limits()

    def test_short_budget_checks_sooner(self):
        searcher = Searcher(tt_size=0)
        searcher.deadline = 10.0
        with patch('search.time.monotonic', return_value=9.97):
            searcher._check_limits()
        self.assertEqual(searcher._next_check, 64)


if __name__ == '__main__':
    unittest.main()
