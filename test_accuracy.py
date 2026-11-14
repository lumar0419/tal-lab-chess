"""Differential rule checks require optional python-chess; production does not."""
import random
import unittest
from board import Board
from search import Searcher
try:
    import chess
except ImportError:
    chess=None

class EvasionTests(unittest.TestCase):
    @unittest.skipIf(chess is None,'optional python-chess not installed')
    def test_random_legal_positions_and_check_evasions(self):
        rng=random.Random(701);positions=0;checks=0
        for game in range(25):
            ref=chess.Board();b=Board()
            for ply in range(160):
                legal=list(ref.legal_moves)
                self.assertEqual({m.uci() for m in legal},{m.uci() for m in b.legal_moves()},b.fen())
                before=b.snapshot()
                if b.in_check():
                    checks+=1;found=[]
                    for m in b.evasion_candidates():
                        b.make_move(m)
                        if not b.is_attacked(b.king_sq[b.side^1],b.side):found.append(m.uci())
                        b.unmake_move()
                    self.assertEqual(set(found),{m.uci() for m in legal},b.fen())
                self.assertEqual(b.snapshot(),before);positions+=1
                if not legal or ref.is_game_over():break
                chosen=rng.choice(legal);ref.push(chosen);b.make_move(b.parse_uci(chosen.uci()))
        self.assertGreater(positions,2000);self.assertGreater(checks,50)
        print(f'Differential positions={positions}, checked positions={checks}')
    def test_same_scores_and_nodes_full_vs_filtered(self):
        fens=['r3k2r/p1ppqpb1/bn2pnp1/2pP4/1p2P3/2N2N2/PPQBBPPP/R3K2R w KQkq - 0 1',
              '7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1',
              '7k/5P2/6K1/8/8/8/8/8 w - - 0 1']
        for fen in fens:
            results=[]
            for enabled in [False,True]:
                s=Searcher(tt_size=20000);s.fast_evasions=enabled;groups=[]
                s.search(Board(fen),max_depth=3,multipv=3,on_info=None,on_multipv=groups.append)
                results.append((s.nodes,[(l.score,[m.uci() for m in l.pv]) for l in groups[-1]]))
            self.assertEqual(results[0],results[1])

if __name__=='__main__':unittest.main(verbosity=2)
