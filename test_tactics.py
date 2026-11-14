"""전술 탐색 회귀 테스트 (v0.4.3).

실행: python test_tactics.py
TacticalChecks는 한 체스 엔진의 실험 옵션이며 다른 엔진을 만들지 않는다.
여기의 FEN은 메이트·체크·희생 미끼를 검사하는 합성 테스트다.
미하일 탈의 실전 기보 또는 인간다운 수의 검증된 점수로 주장하지 않는다.
"""
import unittest

from board import Board
from evaluate import mirror
from search import Searcher, INF, MATE, TimeUp

ROOK_MATE = '7k/8/6K1/8/8/8/8/R7 w - - 0 1'
KNIGHT_PROMOTION_MATE = '6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1'
CAPTURE_KNIGHT_MATE = '5r2/4P1K1/4k3/2Q5/8/8/8/8 w - - 0 1'
CAPTURE_MATE = '7k/6pp/8/7N/8/8/8/6QK w - - 0 1'
STALEMATE = '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1'
DISCOVERED_CHECK = '4k3/8/8/8/8/8/4B3/4R1K1 w - - 0 1'
HORIZON_TRAP = '7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1'


def qscore(fen, check=False):
    s = Searcher(tt_size=2000)
    s.qsearch_quiet_checks = check
    b = Board(fen)
    before = b.snapshot()
    score = s.quiesce(b, -INF, INF, 0)
    assert b.snapshot() == before, 'qsearch changed board state'
    return score, s.nodes


class TacticalChecksTests(unittest.TestCase):
    def test_quiet_rook_mate_white(self):
        off, _ = qscore(ROOK_MATE)
        on, _ = qscore(ROOK_MATE, check=True)
        self.assertLess(off, MATE - 1000)
        self.assertEqual(on, MATE - 1)

    def test_quiet_rook_mate_black(self):
        flipped = mirror(Board(ROOK_MATE)).fen()
        off, _ = qscore(flipped)
        on, _ = qscore(flipped, check=True)
        self.assertLess(off, MATE - 1000)
        self.assertEqual(on, MATE - 1)

    def test_underpromotion_mate_preserved(self):
        for fen in (KNIGHT_PROMOTION_MATE, CAPTURE_KNIGHT_MATE):
            for enabled in (False, True):
                with self.subTest(fen=fen, tactical_checks=enabled):
                    score, _ = qscore(fen, enabled)
                    self.assertEqual(score, MATE - 1)

    def test_capture_mate_preserved(self):
        for enabled in (False, True):
            score, _ = qscore(CAPTURE_MATE, enabled)
            self.assertEqual(score, MATE - 1)

    def test_stalemate_preserved(self):
        for enabled in (False, True):
            self.assertEqual(qscore(STALEMATE, enabled)[0], 0)

    def test_detects_discovered_check(self):
        b = Board(DISCOVERED_CHECK)
        candidate = b.parse_uci('e2f3')
        self.assertIsNotNone(candidate)
        b.make_move(candidate)
        self.assertTrue(b.in_check())     # 움직인 비숍이 아닌 룩의 공격이 열린 체크
        b.unmake_move()
        root = len(b.history)
        visited = []
        original = b.make_move

        def watch(move):
            if len(b.history) == root:
                visited.append(move.uci())
            return original(move)

        b.make_move = watch
        s = Searcher(tt_size=1000)
        s.qsearch_quiet_checks = True
        s.quiesce(b, -INF, INF, 0)
        self.assertIn('e2f3', visited)
        self.assertEqual(b.fen(), DISCOVERED_CHECK)

    def test_horizon_bait_is_recognized(self):
        # 퀸을 잡는 Bxf1 뒤에는 조용한 Ra8#이 가능하다.
        b = Board(HORIZON_TRAP)
        b.push_uci('g2f1')
        mate = b.parse_uci('a1a8')
        self.assertIsNotNone(mate)
        b.make_move(mate)
        self.assertEqual(b.outcome(), ('1-0', '체크메이트'))
        b.unmake_move()
        b.unmake_move()
        before = b.snapshot()
        s1 = Searcher(tt_size=1000)
        m_off, _ = s1.search(b, max_depth=1, on_info=None)
        s2 = Searcher(tt_size=1000)
        s2.qsearch_quiet_checks = True
        m_on, _ = s2.search(b, max_depth=1, on_info=None)
        self.assertEqual(m_off.uci(), 'g2f1')
        self.assertNotEqual(m_on.uci(), 'g2f1')
        self.assertEqual(b.snapshot(), before)

    def test_75_move_mate_priority(self):
        # 조용한 체크가 75수 조건에 닿더라도 메이트가 우선이다.
        f = ROOK_MATE.replace(' - 0 1', ' - 149 1')
        score, _ = qscore(f, check=True)
        self.assertEqual(score, MATE - 1)

    def test_qsearch_stop_restores_board(self):
        b = Board(HORIZON_TRAP)
        start = b.snapshot()
        s = Searcher(tt_size=1000)
        s.qsearch_quiet_checks = True
        s.node_limit = 2
        s._next_check = 2
        with self.assertRaises(TimeUp):
            s.quiesce(b, -INF, INF, 0)
        self.assertEqual(b.snapshot(), start)

    def test_depth_guard_prevents_explosion(self):
        s = Searcher(tt_size=1000)
        s.qsearch_quiet_checks = True
        s.quiesce(Board(DISCOVERED_CHECK), -INF, INF, 0)
        self.assertLess(s.nodes, 1000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
