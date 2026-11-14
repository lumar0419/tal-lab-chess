"""v0.8.8: 정적 교환 평가(SEE)와 선택적 탐색(SelectiveSearch) 회귀 테스트.

기본 Searcher()는 v0.8.7과 같은 전폭 탐색이어야 하고, selective=True는
규칙(메이트·스테일메이트·반복)과 인터페이스(searchmoves·MultiPV·중단 복구)를 깨지 않아야 한다.
"""
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from board import Board, Move, parse_sq
from search import MATE, MATE_BOUND, Searcher, mate_plies

ROOT = Path(__file__).resolve().parent


def move(text):
    return Move(parse_sq(text[:2]), parse_sq(text[2:4]), text[4:])


def selective(**options):
    searcher = Searcher()
    searcher.selective = True
    for key, value in options.items():
        setattr(searcher, key, value)
    return searcher


class StaticExchangeTests(unittest.TestCase):
    def test_known_exchanges(self):
        cases = (
            # 지키는 기물이 없는 폰을 잡음
            ('4k3/8/8/3p4/8/8/8/3RK3 w - - 0 1', 'd1d5', 100),
            # 폰이 지키는 폰을 룩으로 잡음: +100 -500
            ('4k3/8/4p3/3p4/8/8/8/3RK3 w - - 0 1', 'd1d5', -400),
            # 폰으로 나이트를 잡음: 되잡혀도 이득
            ('4k3/8/2p5/3n4/4P3/8/8/4K3 w - - 0 1', 'e4d5', 220),
            # 룩 두 개가 겹쳐 있으면(x-ray) 지켜진 폰도 잡을 수 있다: +100 -500 +500
            ('3rk3/8/8/3p4/8/8/3R4/3RK3 w - - 0 1', 'd2d5', 100),
            # 빈 칸으로 가는 조용한 수: 폰이 노리는 칸에 나이트를 둠
            ('4k3/8/2p5/8/8/2N5/8/4K3 w - - 0 1', 'c3d5', -320),
            # 킹만 되잡을 수 있는 칸: 뒤에서 퀸이 지키면 킹은 잡지 못한다 / 지키지 않으면 비숍을 잃는다
            ('6k1/8/1q6/2b5/8/8/5P2/6K1 b - - 0 1', 'c5f2', 100),
            ('6k1/8/8/2b5/8/8/5P2/6K1 b - - 0 1', 'c5f2', -230),
        )
        for fen, uci, expected in cases:
            with self.subTest(fen=fen, move=uci):
                board = Board(fen)
                before = board.snapshot()
                self.assertEqual(board.see(move(uci)), expected)
                self.assertEqual(board.snapshot(), before)

    def test_en_passant_and_promotion(self):
        board = Board('4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1')
        self.assertEqual(board.see(move('e5d6')), 100)
        board = Board('3r4/4P3/8/8/8/8/8/4K2k w - - 0 1')
        self.assertEqual(board.see(move('e7d8q')), 500 + 900 - 100)
        # 승격한 퀸이 바로 잡힘: 폰 하나를 잃는 셈
        board = Board('3r4/4P3/8/8/8/8/8/4K2k w - - 0 1')
        self.assertEqual(board.see(move('e7e8q')), -100)


class SelectiveSearchTests(unittest.TestCase):
    def test_default_searcher_is_full_width(self):
        searcher = Searcher()
        self.assertFalse(searcher.selective)
        searcher.search(Board(), max_depth=3, on_info=None)
        self.assertEqual(sum(searcher.sel_stats.values()), 0)

    def test_switch_changes_tree_and_clears_tt(self):
        fen = 'r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 3 9'
        searcher = Searcher()
        searcher.search(Board(fen), max_depth=4, on_info=None)
        full_nodes = searcher.nodes
        self.assertGreater(len(searcher.tt), 0)
        searcher.selective = True
        searcher.search(Board(fen), max_depth=1, on_info=None)
        self.assertLess(len(searcher.tt), 100)       # 설정이 바뀌면 이전 점수를 다시 쓰지 않는다
        searcher.search(Board(fen), max_depth=4, on_info=None)
        self.assertLess(searcher.nodes, full_nodes)
        self.assertGreater(sum(searcher.sel_stats.values()), 0)

    def test_forced_mates_are_kept(self):
        cases = (
            ('3qr1k1/5ppp/8/8/8/8/4RPPP/4R1K1 w - - 0 1', 6, 3),        # 2수 메이트
            ('6k1/5ppp/8/8/8/8/8/R3K2R w KQ - 0 1', 3, 1),              # 1수 메이트
            ('r1bk2nr/p2p1pNp/n2B4/1p1NP2P/6P1/3P1Q2/P1P1K3/q5b1 w - - 1 22', 5, 3),  # Anderssen 22.Qf6+
            ('4kb1r/p2n1ppp/4q3/4p1B1/4P3/1Q6/PPP2PPP/2KR4 w k - 0 16', 5, 3),        # Morphy 16.Qb8+
        )
        for fen, depth, plies in cases:
            with self.subTest(fen=fen):
                best, score = selective().search(Board(fen), max_depth=depth, on_info=None)
                self.assertEqual(mate_plies(score), plies)
                self.assertEqual(score, MATE - plies)
                self.assertIsNotNone(best)

    def test_defender_sees_being_mated(self):
        # 흑이 무엇을 두어도 다음 수에 메이트: 가지치기가 메이트 점수를 평가값으로 덮으면 안 된다
        board = Board('6k1/5ppp/8/8/8/8/5PPP/3RR1K1 b - - 0 1')
        _, score = selective().search(board, max_depth=4, on_info=None)
        self.assertLess(score, 0)
        board = Board('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1')            # 스테일메이트
        self.assertEqual(selective().search(board, max_depth=4, on_info=None), (None, 0))

    def test_stalemate_trap_is_avoided(self):
        board = Board('7k/5K1p/7P/8/8/1N6/2PP4/b7 w - - 0 1')       # Nxa1은 스테일메이트
        for depth in (1, 2, 4):
            with self.subTest(depth=depth):
                best, score = selective().search(board, max_depth=depth, on_info=None)
                self.assertNotEqual(best.uci(), 'b3a1')
                self.assertGreater(score, 0)

    def test_repetition_claim_is_still_zero(self):
        board = Board('6k1/8/8/8/8/8/5q2/7K b - - 0 1')
        for uci in ('f2f1', 'h1h2', 'f1f2', 'h2h1', 'f2f1', 'h1h2', 'f1f2', 'h2h1'):
            board.push_uci(uci)
        # 이기고 있는 흑이 같은 국면을 또 만들면 0점이므로 다른 수를 골라야 한다
        best, score = selective().search(board, max_depth=4, on_info=None)
        self.assertGreater(score, 500)
        probe = Board('6k1/8/8/8/8/8/5q2/7K b - - 0 1')
        probe.restore(board.snapshot())
        probe.make_move(best)
        self.assertLess(probe.repetition_count(), 3)

    def test_board_restored_after_node_limit(self):
        board = Board('r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 3 9')
        before = board.snapshot()
        searcher = selective()
        best, _ = searcher.search(board, node_limit=3000, on_info=None)
        self.assertEqual(board.snapshot(), before)
        self.assertEqual(searcher.nodes, 3000)
        self.assertIn(best, board.legal_moves())
        self.assertFalse(searcher._after_null)

    def test_searchmoves_and_multipv(self):
        fen = 'r1b1rnk1/1p4pp/p1p2p2/3pN2n/3P1PPq/2NBPR1P/PPQ5/2R3K1 w - - 0 1'
        best, _ = selective().search(Board(fen), max_depth=4, root_moves=['a2a3', 'c1f1'], on_info=None)
        self.assertIn(best.uci(), ('a2a3', 'c1f1'))
        groups = []
        selective().search(Board(fen), max_depth=4, multipv=3, on_info=None, on_multipv=groups.append)
        self.assertEqual(len(groups), 4)
        last = groups[-1]
        self.assertEqual(len({line.pv[0] for line in last}), 3)
        self.assertEqual([line.score for line in last], sorted((line.score for line in last), reverse=True))
        for line in last:                                  # 표시 수순은 실제로 둘 수 있는 수여야 한다
            replay = Board(fen)
            for step in line.pv:
                self.assertIn(step, replay.legal_moves())
                replay.make_move(step)

    def test_sacrifice_line_protection_finds_bishop_sacrifice_earlier(self):
        # WAC.114: 1.Bxh7+ Nxh7 2.Qg6 — 기물을 내준 뒤 조용한 수로 이어지는 공격.
        # 평가값만 믿는 가지치기는 2.Qg6의 위협을 얕은 깊이에서 놓친다. 보호를 켜면 같은 깊이에서 찾는다.
        fen = 'r1b1rnk1/1p4pp/p1p2p2/3pN2n/3P1PPq/2NBPR1P/PPQ5/2R3K1 w - - 0 1'
        best, score = selective().search(Board(fen), max_depth=5, on_info=None)
        self.assertEqual(best.uci(), 'd3h7')
        self.assertGreater(score, 150)
        self.assertLess(Board(fen).see(best), 0)           # 그 칸에서 기물을 잃는 수 = 희생
        plain, _ = selective(sel_sac_ply=0, sel_qchecks=False).search(Board(fen), max_depth=5, on_info=None)
        self.assertNotEqual(plain.uci(), 'd3h7')

    def test_finds_queen_sacrifices_within_a_budget_where_full_width_search_does_not(self):
        # 전폭 탐색이 3초(20만 노드 이상)에도 못 찾던 WAC의 퀸 희생. 같은 노드 예산으로 비교한다.
        cases = (('r3kb1r/1pp3p1/p3bp1p/5q2/3QN3/1P6/PBP3P1/3RR1K1 w kq - 0 1', 'd4d7', 100_000),
                 ('rn1qr2Q/pbppk1p1/1p2pb2/4N3/3P4/2N5/PPP3PP/R4RK1 w - - 0 1', 'h8g7', 60_000))
        for fen, answer, budget in cases:
            with self.subTest(fen=fen):
                board = Board(fen)
                self.assertLessEqual(board.see(move(answer)), -800)
                searcher = selective()
                best, score = searcher.search(Board(fen), node_limit=budget, on_info=None)
                self.assertEqual(best.uci(), answer)
                full = Searcher()
                other, _ = full.search(Board(fen), node_limit=budget, on_info=None)
                self.assertNotEqual(other.uci(), answer)

    def test_refuses_unsound_queen_offer(self):
        # 퀸을 그냥 내주는 수는 깊이를 늘려도 고르지 않는다
        fen = 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3'
        board = Board(fen)
        best, _ = selective().search(board, max_depth=5, on_info=None)
        self.assertGreaterEqual(board.see(best), 0)

    def test_mate_bound_scores_never_come_from_pruning(self):
        # 조용한 국면에서 가지치기 반환값이 메이트 점수로 둔갑하지 않는다
        for fen in ('r1bq1rk1/pp2ppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/R3KB1R w KQ - 3 9',
                    'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1'):
            with self.subTest(fen=fen):
                _, score = selective().search(Board(fen), max_depth=5, on_info=None)
                self.assertLess(abs(score), MATE_BOUND)


class UciSelectiveTests(unittest.TestCase):
    def run_uci(self, commands, until='uciok'):
        """명령을 보내고 until로 시작하는 줄이 나올 때까지 읽은 뒤 끝낸다 (go 뒤에 바로 quit하면 탐색이 끊김)."""
        process = subprocess.Popen([sys.executable, str(ROOT / 'uci.py')], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True, cwd=ROOT)
        lines = []
        try:
            process.stdin.write('\n'.join(commands) + '\n')
            process.stdin.flush()
            for line in process.stdout:
                lines.append(line.rstrip('\n'))
                if line.startswith(until):
                    break
            process.stdin.write('quit\n')
            process.stdin.flush()
            process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.kill()
            process.stdin.close()
            process.stdout.close()
        return lines

    def test_option_is_advertised_and_switchable(self):
        fen = 'r1b1rnk1/1p4pp/p1p2p2/3pN2n/3P1PPq/2NBPR1P/PPQ5/2R3K1 w - - 0 1'
        lines = self.run_uci(['uci'])
        self.assertIn('option name SelectiveSearch type check default false', lines)
        out = {}
        for value in ('true', 'false'):
            lines = self.run_uci(['uci', f'setoption name SelectiveSearch value {value}', 'isready',
                                  f'position fen {fen}', 'go depth 4'], until='bestmove')
            self.assertFalse([line for line in lines if 'unsupported option' in line])
            best = [line for line in lines if line.startswith('bestmove')]
            self.assertEqual(len(best), 1)
            nodes = [int(line.split(' nodes ')[1].split()[0]) for line in lines
                     if line.startswith('info depth 4 ')]
            out[value] = (best[0].split()[1], nodes[-1])
        reference = Searcher()
        expected, _ = reference.search(Board(fen), max_depth=4, on_info=lambda info: None)
        self.assertEqual(out['false'], (expected.uci(), reference.nodes))   # 끄면 v0.8.7과 같은 전폭 탐색
        self.assertEqual(out['true'][0], 'd3h7')
        self.assertNotEqual(out['true'][1], out['false'][1])



class WebSelectiveTests(unittest.TestCase):
    FEN = 'r1b1rnk1/1p4pp/p1p2p2/3pN2n/3P1PPq/2NBPR1P/PPQ5/2R3K1 w - - 0 1'

    def wait(self, read, done, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            state = read()
            if done(state):
                return state
            time.sleep(.02)
        raise AssertionError('web search did not finish in time')

    def test_analysis_option_runs_selective_multipv(self):
        from analysis_server import AnalysisSession
        session = AnalysisSession(threading.Lock(), search_wait_seconds=3)
        try:
            session.set_fen(self.FEN)
            with self.assertRaises(ValueError):
                session.start({'min_depth': 2, 'max_depth': 3, 'options': {'selective': 'true'}})
            started = session.start({'min_depth': 3, 'max_depth': 5, 'seconds': 20, 'multipv': 3,
                                     'options': {'selective': True}})
            self.assertTrue(started['options']['selective'])
            state = self.wait(session.state, lambda s: not s['active'])
            self.assertEqual(state['status'], 'completed')
            final = state['iterations'][-1]
            self.assertEqual(final['depth'], 5)
            moves = [line['pv'][0] for line in final['candidates']]
            self.assertEqual(len(set(moves)), 3)
            self.assertEqual(moves[0], 'd3h7')            # 비숍 희생이 1위 후보
        finally:
            session.stop()

    def test_game_option_extends_depth_cap_only_when_selective(self):
        from web_server import Game, SELECTIVE_EXTRA_DEPTH
        for enabled in (False, True):
            with self.subTest(selective=enabled):
                game = Game()
                game.new({'side': 'black', 'depth': 2, 'seconds': 5, 'options': {'selective': enabled}})
                state = self.wait(game.state, lambda s: s['moves'] and not s['thinking'])
                self.assertEqual(state['options']['selective'], enabled)
                self.assertEqual(state['info']['depth'], 2 + (SELECTIVE_EXTRA_DEPTH if enabled else 0))


if __name__ == '__main__':
    unittest.main()
