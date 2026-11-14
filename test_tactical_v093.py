"""v0.9.3 전술 프로필(선택적 탐색 + 희생 수 연장)과 새 연장 스위치 회귀 검사.

    python -m unittest test_tactical_v093
"""
import io
import json
import unittest
from pathlib import Path

from board import Board
from search import (MATE, TACTICAL_PROFILE, Searcher, mate_plies)

KASPAROV = "b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24"
ECM_1011 = "r1bqnrk1/pp2ppb1/1np3pp/4P1N1/5P2/2NBB3/PPP3PP/R2Q1RK1 w - - 0 1"
EXTENSIONS = {'sac_extension': 2}


def run(fen, depth, **options):
    searcher = Searcher()
    for key, value in options.items():
        if not hasattr(searcher, key):
            raise AssertionError(f'unknown option {key}')
        setattr(searcher, key, value)
    board = Board(fen)
    before = board.snapshot()
    move, score = searcher.search(board, max_depth=depth, on_info=None)
    assert board.snapshot() == before, 'search must restore the board'
    return move.uci() if move else None, score, searcher


class DefaultsUnchanged(unittest.TestCase):
    """새 스위치는 전부 기본 꺼짐: 기존 탐색의 수·점수·노드 수가 v0.9.2와 같아야 한다."""

    def test_new_switches_default_off(self):
        searcher = Searcher()
        self.assertFalse(searcher.tactical)
        self.assertEqual(searcher.sac_extension, 0)

    def test_fixed_depth_results_match_v092(self):
        # v0.9.2(7a91e38)에서 같은 명령으로 잰 값. 노드 수까지 같아야 기본 경로가 그대로다.
        pinned = (
            ({}, KASPAROV, ('a5c6', -10, 31672)),
            ({}, ECM_1011, ('g5h7', 175, 29607)),
            ({'lmr': True}, KASPAROV, ('a5c6', -10, 28702)),
            ({'selective': True}, KASPAROV, ('a5c6', -10, 24382)),
            ({'selective': True}, ECM_1011, ('g5h7', 175, 10375)),
        )
        for options, fen, expected in pinned:
            move, score, searcher = run(fen, 4, **options)
            self.assertEqual((move, score, searcher.nodes), expected, (options, fen))
            self.assertFalse(searcher.ext_stats, 'no extension may fire when switched off')


class ProfileSwitch(unittest.TestCase):
    def test_set_tactical_applies_and_restores(self):
        searcher = Searcher()
        searcher.set_tactical(True)
        self.assertTrue(searcher.tactical)
        for key, value in TACTICAL_PROFILE.items():
            self.assertEqual(getattr(searcher, key), value, key)
        searcher.set_tactical(False)
        self.assertFalse(searcher.tactical)
        self.assertEqual(searcher.sac_extension, 0)
        # selective는 부르는 쪽 설정이므로 끌 때 건드리지 않는다.
        self.assertTrue(searcher.selective)

    def test_set_tactical_false_keeps_manual_switches(self):
        searcher = Searcher()
        searcher.sac_extension = 1
        searcher.set_tactical(False)          # 켠 적이 없으면 수동 설정을 지우지 않음
        self.assertEqual(searcher.sac_extension, 1)

    def test_switch_change_clears_tt_scores(self):
        searcher = Searcher()
        searcher.selective = True
        board = Board(KASPAROV)
        searcher.search(board, max_depth=3, on_info=None)
        self.assertGreater(len(searcher.tt), 0)
        searcher.sac_extension = 2
        searcher.search(board, max_depth=1, on_info=None)
        # 다른 연장 설정의 점수를 재사용하지 않도록 새 탐색 시작 때 비워졌어야 한다.
        self.assertLess(len(searcher.tt), 200)

    def test_profiles_registry_matches(self):
        from research.tactical_profiles import PROFILES
        self.assertEqual(PROFILES['tactical'], TACTICAL_PROFILE)


class ExtensionsStaySound(unittest.TestCase):
    def test_known_mates_keep_their_distance(self):
        cases = json.loads((Path(__file__).parent / 'research' / 'tactics.json').read_text('utf-8'))
        checked = 0
        for case in cases:
            if 'mate_plies' not in case:
                continue
            depth = case['mate_plies'] + 1
            _, plain, _ = run(case['fen'], depth)
            for options in ({'sac_extension': 3}, dict(TACTICAL_PROFILE)):
                _, score, _ = run(case['fen'], depth, **options)
                self.assertEqual(mate_plies(score), mate_plies(plain), (case['id'], options))
                self.assertEqual(score > 0, plain > 0, case['id'])
            checked += 1
        self.assertGreater(checked, 0)

    def test_mate_in_one_and_stalemate_scores(self):
        for options in ({}, {'selective': True, **EXTENSIONS}):
            move, score, _ = run("7k/8/6K1/8/8/8/8/R7 w - - 0 1", 3, **options)
            self.assertEqual((move, score), ('a1a8', MATE - 1))
            # 스테일메이트를 피해야 이기는 국면: 연장이 켜져도 무승부 수를 고르지 않는다.
            move, score, _ = run("7k/5K2/6Q1/8/8/8/8/8 w - - 0 1", 3, **options)
            self.assertGreater(score, MATE - 10)

    def test_sacrifice_extension_counts_only_material_offers(self):
        # 시작 국면 깊이 2: 루트에 기물을 그냥 내주는 수가 없다 → 연장 0회.
        _, _, quiet = run("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", 2,
                          selective=True, sac_extension=2)
        self.assertEqual(quiet.ext_stats['sac'], 0)
        _, _, sharp = run(KASPAROV, 2, selective=True, sac_extension=2)
        self.assertGreater(sharp.ext_stats['sac'], 0)

    def test_sacrifice_extension_searches_offer_deeper(self):
        # Rxd4(기물 희생)만 루트 후보로 두면, 연장 2는 명목 깊이 2에서 연장 없는 깊이 4와 같은 점수.
        def only_rxd4(depth, **options):
            searcher = Searcher()
            for key, value in options.items():
                setattr(searcher, key, value)
            return searcher.search(Board(KASPAROV), max_depth=depth, on_info=None,
                                   root_moves=['d1d4'])[1]
        self.assertEqual(only_rxd4(2, sac_extension=2), only_rxd4(4))

    def test_time_limited_tactical_search_restores_board(self):
        searcher = Searcher()
        searcher.set_tactical(True)
        board = Board(KASPAROV)
        before = board.snapshot()
        move, _ = searcher.search(board, time_limit=0.3, on_info=None)
        self.assertEqual(board.snapshot(), before)
        self.assertIn(move, board.legal_moves())


class Integration(unittest.TestCase):
    def test_deep_profile_and_cli_choice(self):
        import deep_analysis
        self.assertIn('tactical', deep_analysis.PROFILES)
        searcher = deep_analysis.make_searcher('tactical')
        self.assertTrue(searcher.tactical and searcher.selective and not searcher.lmr)
        self.assertFalse(deep_analysis.make_searcher('conservative').tactical)
        with self.assertRaises(ValueError):
            deep_analysis.make_searcher('nope')

    def test_multipv_lines_are_distinct_legal_moves(self):
        searcher = Searcher()
        searcher.set_tactical(True)
        board = Board(KASPAROV)
        groups = []
        searcher.search(board, max_depth=3, multipv=3, on_info=None, on_multipv=groups.append)
        self.assertEqual([group[0].depth for group in groups], [1, 2, 3])
        firsts = [line.pv[0] for line in groups[-1]]
        self.assertEqual(len(set(firsts)), 3)
        self.assertTrue(set(firsts) <= set(board.legal_moves()))
        scores = [line.score for line in groups[-1]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_analysis_session_runs_tactical_past_the_depth_cap(self):
        import threading
        import analysis_server
        session = analysis_server.AnalysisSession(threading.Lock(), background=False)
        session.set_fen("8/8/8/4k3/8/8/4P3/4K3 w - - 0 1")
        base = dict(min_depth=1, max_depth=5, seconds=10, multipv=1)
        session.start({**base, 'options': {'tactical': True}})
        state = session.state()
        self.assertTrue(state['options']['tactical'])
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['completed']['depth'], 5 + analysis_server.TACTICAL_EXTRA_DEPTH)
        session.start({**base, 'options': {}})
        self.assertEqual(session.state()['completed']['depth'], 5)

    def test_server_option_keys(self):
        import analysis_server
        import web_server
        self.assertIn('tactical', analysis_server.ANALYSIS_OPTION_KEYS)
        self.assertIn('tactical', web_server.OPTION_KEYS)
        self.assertFalse(web_server.DEFAULT_OPTIONS['tactical'])

    def test_uci_option_toggles_profile(self):
        from uci import UCIEngine
        out = io.StringIO()
        engine = UCIEngine(out=out)
        engine.handle('uci')
        self.assertIn('option name TacticalSearch type check default false', out.getvalue())
        engine.handle('setoption name TacticalSearch value true')
        self.assertTrue(engine.searcher.tactical and engine.searcher.selective)
        self.assertEqual(engine.searcher.sac_extension, TACTICAL_PROFILE['sac_extension'])
        engine.handle('setoption name TacticalSearch value false')
        self.assertFalse(engine.searcher.tactical or engine.searcher.selective)
        self.assertEqual(engine.searcher.sac_extension, 0)
        # SelectiveSearch를 따로 켠 상태는 전술 프로필을 꺼도 유지된다.
        engine.handle('setoption name SelectiveSearch value true')
        engine.handle('setoption name TacticalSearch value true')
        engine.handle('setoption name TacticalSearch value false')
        self.assertTrue(engine.searcher.selective)


if __name__ == '__main__':
    unittest.main()
