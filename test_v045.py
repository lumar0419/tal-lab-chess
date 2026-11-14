"""v0.4.5: initiative option, symmetry, legacy invariants, sacrifice analysis."""
import io
import unittest

import evaluate
from board import Board, START_FEN
from evaluate import evaluate_white, evaluate_white_terms, initiative_terms, mirror
from analyze_sacrifices import compare_candidates
from search import Searcher, MATE, INF
from uci import UCIEngine


TACTICAL = '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'
PRESSURE = '4k3/8/8/3q4/5N2/8/8/4K3 w - - 0 1'
NO_PRESSURE = '4k3/8/8/8/5N2/8/8/4K3 w - - 0 1'


class InitiativeTests(unittest.TestCase):
    def setUp(self):
        self.saved = (evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY, evaluate.KING_SAFETY)

    def tearDown(self):
        evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY, evaluate.KING_SAFETY = self.saved

    def test_default_off(self):
        self.assertFalse(evaluate.INITIATIVE)

    def test_start_is_neutral(self):
        self.assertEqual(initiative_terms(Board()), (0, 0))

    def test_valuable_piece_pressure(self):
        self.assertGreater(initiative_terms(Board(PRESSURE))[0], 0)
        self.assertEqual(initiative_terms(Board(NO_PRESSURE)), (0, 0))

    def test_slider_pressure_needs_clear_line(self):
        open_line = Board('7k/8/8/8/8/3q4/8/1B5K w - - 0 1')
        blocked = Board('7k/8/8/8/8/3q4/2R5/1B5K w - - 0 1')
        self.assertGreater(initiative_terms(open_line)[0], 0)
        self.assertEqual(initiative_terms(blocked), (0, 0))

    def test_no_unconditional_material_reward(self):
        for fen in (PRESSURE, NO_PRESSURE, START_FEN, TACTICAL):
            mg, eg = initiative_terms(Board(fen))
            self.assertLessEqual(abs(mg), evaluate.INITIATIVE_CAP)
            self.assertLessEqual(abs(eg), 12)

    def test_mirror_all_feature_combinations(self):
        from pathlib import Path
        fens = [PRESSURE, NO_PRESSURE, START_FEN, TACTICAL]
        path = Path(__file__).with_name('v044_positions.txt')
        fens += [s for s in path.read_text().splitlines() if s and not s.startswith('#')][::11]
        for ini in (False, True):
            for act in (False, True):
                for ks in (False, True):
                    evaluate.INITIATIVE = ini
                    evaluate.ATTACK_ACTIVITY = act
                    evaluate.KING_SAFETY = ks
                    for fen in fens:
                        b = Board(fen)
                        self.assertEqual(evaluate_white(b), evaluate_white_terms(b),
                                         (ini, act, ks, fen))
                        self.assertEqual(evaluate_white(b), -evaluate_white(mirror(b)),
                                         (ini, act, ks, fen))

    def test_tactical_mate_and_state(self):
        evaluate.INITIATIVE = True
        b = Board(TACTICAL)
        old = b.snapshot()
        for checks in (False, True):
            searcher = Searcher(tt_size=1000)
            searcher.qsearch_quiet_checks = checks
            best, score = searcher.search(b, max_depth=2, on_info=None)
            self.assertEqual(best.uci(), 'f7f8n')
            self.assertEqual(score, MATE - 1)
            self.assertEqual(b.snapshot(), old)

    def test_uci_toggle_clears_tt(self):
        output = io.StringIO()
        engine = UCIEngine(out=output)
        engine.handle('uci')
        self.assertIn('option name Initiative type check default false', output.getvalue())
        engine.searcher.tt.store(123456, 2, 0, 20, None)
        self.assertEqual(len(engine.searcher.tt), 1)
        engine.handle('setoption name Initiative value true')
        self.assertTrue(evaluate.INITIATIVE)
        self.assertEqual(len(engine.searcher.tt), 0)
        engine.handle('setoption name Initiative value false')
        self.assertFalse(evaluate.INITIATIVE)

    def test_uci_subprocess_toggle(self):
        from test_uci import Engine
        e = Engine()
        try:
            e.send('uci')
            line, lines, _ = e.wait_for(lambda l: l == 'uciok', 5)
            self.assertEqual(line, 'uciok')
            self.assertIn('option name Initiative type check default false', lines)
            e.send('position fen ' + PRESSURE)
            scores = []
            for flag in ('false', 'true', 'false'):
                e.send('setoption name Initiative value ' + flag)
                e.send('go depth 2')
                move, got, _ = e.bestmove(10)
                self.assertIsNotNone(Board(PRESSURE).parse_uci(move))
                scores.append([line for line in got if line.startswith('info depth 2 ')][-1])
            # Expected root score and bestmove should reproduce after turning the option off.
            self.assertEqual(scores[0].split('score ')[1].split(' nodes')[0],
                             scores[2].split('score ')[1].split(' nodes')[0])
        finally:
            e.close()
            if e.p.stdin and not e.p.stdin.closed:
                e.p.stdin.close()
            if e.p.stdout and not e.p.stdout.closed:
                e.p.stdout.close()

    def test_sacrifice_diagnostic_does_not_change_board(self):
        b = Board(TACTICAL)
        snap = b.snapshot()
        rows = compare_candidates(b, ['f7f8n', 'f7f8q'], 2, initiative=True)
        self.assertEqual(b.snapshot(), snap)
        self.assertEqual({r['move'] for r in rows}, {'f7f8n', 'f7f8q'})
        self.assertEqual({r['move']:r['score'] for r in rows}['f7f8n'], MATE-1)
        self.assertEqual({r['move']:r['score'] for r in rows}['f7f8q'], 0)

    def test_sacrifice_diagnostic_rejects_illegal_move(self):
        with self.assertRaises(ValueError):
            compare_candidates(Board(), ['e2e5'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
