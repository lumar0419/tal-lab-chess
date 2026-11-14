import unittest

from board import Board
from research.deep_sacrifice import classify, prove_short_mate, tal_search
from research.sacrifice_cases import positions, replay_case


class SacrificeResearchTests(unittest.TestCase):
    def test_historical_positions_and_moves_replay(self):
        cases = positions()
        self.assertGreaterEqual(len(cases), 18)
        self.assertGreaterEqual(len({case['master'] for case in cases}), 7)
        for case in cases:
            with self.subTest(case=case['id']):
                replay_case(case)

    def test_independent_short_mate_proof_and_shallow_candidate(self):
        board = Board('r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22')
        self.assertTrue(prove_short_mate(board, 'f3f6', 3))
        self.assertFalse(prove_short_mate(board, 'f3f6', 1))
        self.assertFalse(prove_short_mate(board, 'f3f6', 3, node_budget=0))
        self.assertFalse(prove_short_mate(board, 'f3f6', 7))
        best = tal_search(board, depth=3, seconds=2, multipv=3)
        forced = tal_search(board, depth=3, seconds=2, forced='f3f6')
        result = classify(board, 'f3f6', best, forced)
        self.assertEqual(result['status'], 'verified_tactical_sacrifice')
        self.assertTrue(result['profile']['ends_in_attacker_mate'])
        self.assertIn(result['best_defense'], ('g8f6', 'g8e7'))

    def test_queen_blunder_stays_unconfirmed_until_deep(self):
        board = Board('7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1')
        shallow = tal_search(board, depth=2, seconds=2)
        offer = tal_search(board, depth=2, seconds=2, forced='e2e4')
        self.assertEqual(classify(board, 'e2e4', shallow, offer)['status'],
                         'sacrifice_candidate')
        best = tal_search(board, depth=6, seconds=5)
        forced = tal_search(board, depth=6, seconds=5, forced='e2e4')
        judgment = classify(board, 'e2e4', best, forced)
        self.assertEqual(judgment['status'], 'unfavorable_sacrifice')
        self.assertEqual(judgment['best_defense'], 'd5e4')

    def test_stable_cp_needs_independent_defense_and_is_not_proof(self):
        board = Board('7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1')
        def history(move, score, pv):
            return {'iterations': [
                {'depth': depth, 'lines': [{'depth': depth, 'move': move,
                                            'score': score, 'pv': pv}]}
                for depth in (5, 6)]}
        best = history('e2h5', 100, ['e2h5'])
        forced = history('e2e4', 90, ['e2e4', 'd5e4'])
        defense = {'depth': 5, 'lines': [{'move':'d5e4','attacker_score':85}]}
        result = classify(board, 'e2e4', best, forced)
        self.assertEqual(result['status'], 'sacrifice_candidate')
        result = classify(board, 'e2e4', best, forced, defense)
        self.assertEqual(result['status'], 'engine_supported_sacrifice')
        self.assertFalse(result['verification']['proof'])
        defense['lines'][0]['attacker_score'] = -140
        self.assertEqual(classify(board,'e2e4',best,forced,defense)['status'],
                         'sacrifice_candidate')
