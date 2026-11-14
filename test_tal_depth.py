"""v0.4.8 depth diagnosis regression tests; do not require Stockfish."""
import json
from pathlib import Path
import tempfile
import unittest
from version import VERSION
from unittest.mock import patch

import evaluate
from board import Board
from tal_depth_diagnostic import (
    depths_from_string, verify_pv, run_root, root_static_score,
    diagnose_one, run_diagnostic, main
)
from tal_style_benchmark import load_data, profile_settings


class TalDepthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cases = load_data()
        cls.case = next(c for c in cases if c['id'] == 'botvinnik_tal_1960_g6_ply42')

    def test_depths(self):
        self.assertEqual(depths_from_string('1,2,4'), [1, 2, 4])
        for bad in ('', '0,1', '1,8', '2,2', '3,1', 'hello', '1,,2'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    depths_from_string(bad)

    def test_pv_legality(self):
        board = Board(self.case['fen'])
        good = board.parse_uci(self.case['tal_move'])
        self.assertEqual(verify_pv(self.case['fen'], [good]), [self.case['tal_move']])
        # E1E2 is not a legal move in this case.
        from board import Move, parse_sq
        with self.assertRaises(AssertionError):
            verify_pv(self.case['fen'], [Move(parse_sq('a2'), parse_sq('a3'))])

    def test_root_forced_is_actually_forced_and_pv_legal(self):
        with profile_settings('baseline') as tactical:
            x = run_root(self.case['fen'], 2, tactical, root_move=self.case['tal_move'])
        self.assertEqual(x['move'], self.case['tal_move'])
        self.assertEqual(x['completed_depth'], 2)
        self.assertEqual(x['pv'][0], self.case['tal_move'])
        self.assertGreater(x['nodes'], 0)

    def test_static_and_snapshot(self):
        board = Board(self.case['fen'])
        before = board.snapshot()
        old = evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY
        x = root_static_score(self.case['fen'], self.case['tal_move'])
        self.assertIsInstance(x['static_eval_after_move_cp'], int)
        self.assertIsInstance(x['immediate_material_delta_cp'], int)
        self.assertEqual(board.snapshot(), before)
        self.assertEqual((evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY), old)

    def test_depth_diagnostic_and_score_bounds(self):
        old = evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY
        row = diagnose_one(self.case, 'baseline', [1, 2])
        self.assertEqual([r['depth'] for r in row['depth_results']], [1, 2])
        self.assertEqual(row['historical_move'], self.case['tal_move'])
        for result in row['depth_results']:
            self.assertEqual(result['historical_forced']['move'], self.case['tal_move'])
            self.assertIn(result['selected']['move'], [m.uci() for m in Board(self.case['fen']).legal_moves()])
            self.assertEqual(result['historical_forced']['pv'][0], self.case['tal_move'])
            self.assertIsInstance(result['approx_score_gap_cp'], int)
        self.assertEqual((evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY), old)

    def test_mocked_external_only_when_explicit(self):
        fake_best = {'score':'Cp(+100)', 'score_cp_equivalent':100}
        fake_tal = {'score':'Cp(+80)', 'score_cp_equivalent':80}
        with patch('tal_depth_diagnostic.stockfish_review', return_value=(fake_best, {self.case['tal_move']:fake_tal})) as mock:
            report = run_diagnostic([self.case], ['baseline'], [1], stockfish='fake-sf', sf_depth=8)
            mock.assert_called_once()
        self.assertEqual(report['external_stockfish'][self.case['id']]['historical_root_forced'], fake_tal)
        self.assertEqual(report['engine_version'], VERSION)

    def test_cli_report_and_no_imaginary_external_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'report.json'
            data = main(['--case', self.case['id'], '--profiles', 'baseline',
                         '--depths', '1', '--json-output', str(dest)])
            self.assertTrue(dest.exists())
            raw = json.loads(dest.read_text(encoding='utf-8'))
            self.assertEqual(len(raw['cases']), 1)
            self.assertEqual(raw['external_stockfish'], {})
            self.assertEqual(data['cases'][0]['historical_move'], self.case['tal_move'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
