"""Historical Tal suite: source transcription integrity and one-engine diagnostics."""
import copy
import tempfile
import unittest
from pathlib import Path

import evaluate
from board import Board
from tal_style_benchmark import (load_data, validate_data, immediate_signals,
                                 evaluate_case, summarize, profile_settings, PROFILE_FLAGS, main)


class TalHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games, cls.cases = load_data()

    def test_independent_replay_matches_all_fens(self):
        # Checks all recorded source moves and that selected FENs come from those games.
        self.assertEqual(validate_data(self.games, self.cases), (4, 22))

    def test_critical_decisions_metadata_and_coverage(self):
        ids = [c['id'] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({c['game_id'] for c in self.cases}), 4)
        self.assertTrue(all(c['fen'] and c['source'].startswith('https://') for c in self.cases))
        self.assertTrue(any(c['game_id'].startswith('botvinnik_tal') for c in self.cases))
        self.assertTrue(any(c['theme'].endswith('sacrifice') or 'offer' in c['theme'] for c in self.cases))

    def test_data_detects_corrupt_moves_and_stale_fens(self):
        cases = copy.deepcopy(self.cases)
        cases[0]['tal_move'] = 'a1a2'
        with self.assertRaisesRegex(AssertionError, 'differs'):
            validate_data(self.games, cases)
        cases = copy.deepcopy(self.cases)
        cases[0]['fen'] = Board().fen()
        with self.assertRaisesRegex(AssertionError, 'FEN differs'):
            validate_data(self.games, cases)

    def test_profile_switch_restores_global_configuration(self):
        old = evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY
        for profile in PROFILE_FLAGS:
            with profile_settings(profile) as tactical:
                self.assertEqual(tactical, PROFILE_FLAGS[profile][0])
                self.assertEqual(evaluate.ATTACK_ACTIVITY, PROFILE_FLAGS[profile][1])
                self.assertEqual(evaluate.INITIATIVE, PROFILE_FLAGS[profile][2])
            self.assertEqual((evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY), old)
        with self.assertRaisesRegex(ValueError, 'deliberate'):
            with profile_settings('combined'):
                raise ValueError('deliberate')
        self.assertEqual((evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY), old)

    def test_move_signals_and_non_mutation(self):
        for c in self.cases:
            board = Board(c['fen'])
            snap = board.snapshot()
            signals = immediate_signals(c['fen'], c['tal_move'])
            self.assertIsInstance(signals['gives_check'], bool)
            self.assertIsInstance(signals['captures'], bool)
            self.assertIsInstance(signals['moves_into_attack'], bool)
            self.assertIsInstance(signals['exposed_to_capture_after'], bool)
            self.assertEqual(board.snapshot(), snap)
        # A known knight offer in the 1960 World Championship game.
        knight = self.cases[0]
        self.assertEqual(knight['tal_move'], 'h5f4')
        self.assertTrue(immediate_signals(knight['fen'], knight['tal_move'])['exposed_to_capture_after'])

    def test_search_and_forced_history_compare(self):
        old = evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY
        for c in self.cases[::7]:
            b = Board(c['fen'])
            before = b.snapshot()
            row = evaluate_case(c, 'baseline', depth=1)
            self.assertIn(row['selected_uci'], {m.uci() for m in b.legal_moves()})
            self.assertEqual(row['historical_forced_score_display'] is None, False)
            self.assertEqual(row['historical_uci'], c['tal_move'])
            self.assertEqual(b.snapshot(), before)
        self.assertEqual((evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY), old)

    def test_summary_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'tal_results.json'
            result = main(['--quick', '--depth', '1', '--profiles', 'baseline',
                           '--no-forced', '--json-output', str(dest)])
            self.assertEqual(result['baseline']['positions'], 4)
            self.assertTrue(dest.exists())
            self.assertIn('historical_match_rate', dest.read_text(encoding='utf-8'))
            self.assertEqual(result['baseline']['positions'], 4)


if __name__ == '__main__':
    unittest.main(verbosity=2)
