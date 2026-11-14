import unittest

from board import Board
from research.deep_sacrifice import analyze_defenses, candidate_history, classify


class DepthEvidenceTests(unittest.TestCase):
    @staticmethod
    def group(depth, *moves):
        return {'depth': depth, 'lines': [
            {'depth': depth, 'move': pv[0], 'score': score, 'pv': list(pv)}
            for score, *pv in moves]}

    def test_keeps_rank_pv_and_material_when_rank_changes(self):
        board = Board('7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1')
        g = self.group
        unrestricted = {'iterations': [
            g(1, (90, 'e2h5')), g(2, (100, 'e2h5'), (85, 'e2e4', 'd5e4'))]}
        forced = {'iterations': [
            g(1, (-10, 'e2e4')), g(2, (-700, 'e2e4', 'd5e4'))]}
        rows = candidate_history(board, 'e2e4', unrestricted, forced)
        self.assertEqual([r['unrestricted_rank'] for r in rows], [None, 2])
        self.assertEqual(rows[1]['unrestricted_score'], 85)
        self.assertEqual(rows[1]['pv_defense'], 'd5e4')
        self.assertLess(rows[1]['material_and_checks']['final_material_delta_cp'], 0)
        defense = analyze_defenses(board, 'e2e4', depth=3, seconds=2)
        self.assertEqual(defense['iterations'][-1]['lines'], defense['lines'])
        self.assertEqual(defense['lines'][0]['move'], 'd5e4')

    def test_old_defender_depth_cannot_support_deeper_claim(self):
        board = Board('7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1')
        g = self.group
        best = {'iterations': [g(d, (100, 'e2h5')) for d in (7, 8)]}
        forced = {'iterations': [g(d, (90, 'e2e4', 'd5e4')) for d in (7, 8)]}
        defense = {'depth': 5, 'lines': [{'move': 'd5e4', 'attacker_score': 85}]}
        self.assertEqual(classify(board, 'e2e4', best, forced, defense)['status'],
                         'sacrifice_candidate')
        defense['depth'] = 7
        decision = classify(board, 'e2e4', best, forced, defense)
        self.assertEqual(decision['status'], 'engine_supported_sacrifice')
        self.assertFalse(decision['verification']['proof'])
