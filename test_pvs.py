"""v0.4.9 PVS: full-window equivalence, bounds, draw/mate, UCI, state safety.

Run: python test_pvs.py
External Stockfish and python-chess are not required.
"""
import random
import unittest

from board import Board, START_FEN
from perft import TESTS
from search import Searcher, INF, MATE
from tal_style_benchmark import load_data, profile_settings


def run(fen, depth, pvs, root_moves=None, tt_size=30000, tactical=False):
    b = Board(fen)
    before = b.snapshot()
    s = Searcher(tt_size=tt_size)
    s.pvs = pvs
    s.qsearch_quiet_checks = tactical
    move, score = s.search(b, max_depth=depth, on_info=None, root_moves=root_moves)
    assert b.snapshot() == before, f'board changed by search: {fen}'
    assert move is None or move in b.legal_moves(), f'illegal result {move}: {fen}'
    return move.uci() if move else None, score, s.nodes, s.pvs_probes, s.pvs_researches


def positions():
    _, cases = load_data()
    result = [START_FEN] + [f for _, f, _ in TESTS]
    result += [c['fen'] for c in cases if c.get('featured')]
    result += [
        '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1',
        '5r2/4P1K1/4k3/2Q5/8/8/8/8 w - - 0 1',
        '8/8/8/8/8/5kr1/5p1K/6r1 b - - 0 1',
        '7k/8/6K1/8/8/8/8/R7 w - - 0 1',
        '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1',
        '8/8/8/4k3/8/8/8/R3K3 w - - 98 100',
    ]
    return list(dict.fromkeys(result))


def random_fens(seed=911, count=20):
    rng = random.Random(seed)
    result = []
    for i in range(count):
        b = Board(START_FEN if i % 2 == 0 else TESTS[2][1])
        for _ in range(rng.randint(6, 35)):
            if b.outcome() is not None:
                break
            moves = b.legal_moves()
            if not moves:
                break
            b.make_move(rng.choice(moves))
        if b.outcome() is None:
            result.append(b.fen())
    return result


class PVSTests(unittest.TestCase):
    def test_default_on_and_active_counters(self):
        s = Searcher()
        self.assertTrue(s.pvs)  # search-equivalent and faster in controlled depth tests
        _, _, _, probes, _ = run(TESTS[1][1], 3, True)
        self.assertGreater(probes, 0)
        _, _, _, probes, retries = run(TESTS[1][1], 3, False)
        self.assertEqual((probes, retries), (0, 0))

    def test_full_window_reference_positions(self):
        for fen in positions():
            with self.subTest(fen=fen):
                old = run(fen, 4, False)
                new = run(fen, 4, True)
                self.assertEqual(new[:2], old[:2])

    def test_random_positions(self):
        for fen in random_fens():
            with self.subTest(fen=fen):
                old = run(fen, 3, False)
                new = run(fen, 3, True)
                self.assertEqual(new[1], old[1])
                self.assertIn(new[0], [m.uci() for m in Board(fen).legal_moves()])

    def test_tt_disabled_and_enabled(self):
        for fen in (TESTS[1][1], TESTS[5][1], positions()[9]):
            for tt_size in (0, 30000):
                with self.subTest(fen=fen, tt_size=tt_size):
                    # Without TT the branching factor can be enormous (check extension).
                    # Depth 3 still exercises null-window search and all TT-disabled paths.
                    depth = 3 if tt_size == 0 else 4
                    old = run(fen, depth, False, tt_size=tt_size)
                    new = run(fen, depth, True, tt_size=tt_size)
                    self.assertEqual(old[:2], new[:2])

    def test_root_searchmoves_and_tt_reuse(self):
        for fen, moves in ((START_FEN, ['e2e4', 'd2d4']),
                           ('6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1', ['f7f8q', 'f7f8n']),
                           (TESTS[1][1], ['e1g1', 'e2a6'])):
            with self.subTest(fen=fen):
                self.assertEqual(run(fen, 4, False, root_moves=moves)[:2],
                                 run(fen, 4, True, root_moves=moves)[:2])
        b = Board(TESTS[1][1]); snapshot = b.snapshot()
        s = Searcher(tt_size=10000); s.pvs = True
        r1 = s.search(b, max_depth=4, on_info=None)
        r2 = s.search(b, max_depth=4, on_info=None)
        fresh = Searcher(tt_size=10000); fresh.pvs = False
        r3 = fresh.search(b, max_depth=4, on_info=None)
        self.assertEqual(r1, r2)
        self.assertEqual(r2, r3)
        self.assertEqual(b.snapshot(), snapshot)

    def test_alpha_beta_bounds(self):
        # Full-window exact value is the reference. Null-window searches may return
        # bounds, not exact values: compare to the required bound direction.
        for fen in (START_FEN, TESTS[2][1], TESTS[5][1], positions()[9]):
            exact = run(fen, 3, False)[1]
            windows = ((-INF, INF), (exact - 50, exact + 50),
                       (exact - 200, exact - 100), (exact + 100, exact + 200),
                       (exact - 1, exact), (exact, exact + 1))
            for lo, hi in windows:
                for active in (False, True):
                    with self.subTest(fen=fen, lo=lo, hi=hi, pvs=active):
                        b = Board(fen); snapshot = b.snapshot()
                        s = Searcher(tt_size=30000); s.pvs = active
                        observed = s.negamax(b, 3, lo, hi, 0)
                        self.assertEqual(b.snapshot(), snapshot)
                        if lo < exact < hi:
                            self.assertEqual(observed, exact)
                        elif exact >= hi:
                            self.assertGreaterEqual(observed, hi)
                        else:
                            self.assertLessEqual(observed, lo)

    def test_stopping_and_state(self):
        for fen in (START_FEN, TESTS[1][1]):
            b = Board(fen); snapshot = b.snapshot()
            s = Searcher(); s.pvs = True
            m, _ = s.search(b, node_limit=131, on_info=None)
            self.assertEqual(b.snapshot(), snapshot)
            self.assertLessEqual(s.nodes, 131)
            self.assertIn(m, b.legal_moves())

    def test_mates_and_draws(self):
        for fen, expected_score in (
            ('6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1', MATE - 1),
            ('5r2/4P1K1/4k3/2Q5/8/8/8/8 w - - 0 1', MATE - 1),
            ('7k/8/6K1/8/8/8/8/R7 w - - 0 1', MATE - 1),
            ('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', 0),
        ):
            with self.subTest(fen=fen):
                old = run(fen, 4, False)
                new = run(fen, 4, True)
                self.assertEqual(old[:2], new[:2])
                self.assertEqual(new[1], expected_score)

    def test_pvs_with_aggressive_profile(self):
        _, cases = load_data()
        fens = [c['fen'] for c in cases if c.get('featured')]
        for profile in ('baseline', 'combined'):
            with profile_settings(profile) as tactical:
                for fen in fens:
                    with self.subTest(profile=profile, fen=fen):
                        off = run(fen, 3, False, tactical=tactical)
                        on = run(fen, 3, True, tactical=tactical)
                        self.assertEqual(off[1], on[1])

    def test_uci_option(self):
        # GUI-facing end-to-end test via a separate subprocess.
        from test_uci import Engine
        e = Engine()
        try:
            e.send('uci')
            line, seen, _ = e.wait_for(lambda x: x == 'uciok', 5)
            self.assertEqual(line, 'uciok')
            self.assertIn('option name PVS type check default true', seen)
            for active in (False, True):
                e.send('setoption name PVS value ' + str(active).lower())
                e.send('position fen 6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1')
                e.send('go depth 4')
                move, info, _ = e.bestmove(5)
                self.assertEqual(move, 'f7f8n')
                self.assertTrue(any('score mate 1 ' in x for x in info))
        finally:
            e.close()
            for stream in (e.p.stdin, e.p.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
