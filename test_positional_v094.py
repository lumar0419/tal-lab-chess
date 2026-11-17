"""Evaluation explanation, isolation, research leakage and trace regressions."""
import itertools
import json
import random
import threading
import unittest
from urllib.request import Request, urlopen

from board import Board
import evaluate
from search import Searcher
from analysis_server import AnalysisSession
from research.positional_v094 import features, score_white, INITIAL, candidate
from research.pruning_trace import PruningTrace


class BreakdownTests(unittest.TestCase):
    def test_fast_slow_breakdown_and_mirror(self):
        rng=random.Random(9417);b=Board();positions=[]
        for _ in range(70):
            moves=b.legal_moves()
            if not moves: break
            b.make_move(rng.choice(moves));positions.append(b.fen())
        flags=('KING_SAFETY','ATTACK_ACTIVITY','INITIATIVE')
        saved=[getattr(evaluate,k) for k in flags]
        try:
            for setting in itertools.product((False,True),repeat=3):
                for k,v in zip(flags,setting):setattr(evaluate,k,v)
                for fen in positions:
                    b=Board(fen);rep=evaluate.evaluation_breakdown(b)
                    self.assertEqual(rep['static_score'],evaluate.evaluate_white(b))
                    self.assertEqual(rep['static_score'],evaluate.evaluate_white_terms(b))
                    self.assertEqual(rep['unrounded_numerator'],sum(t['numerator'] for t in rep['terms'].values()))
                    self.assertEqual(rep['static_score'],-evaluate.evaluate_white(evaluate.mirror(b)))
        finally:
            for k,v in zip(flags,saved):setattr(evaluate,k,v)

    def test_explicit_options_do_not_mutate_global_state(self):
        flags=(evaluate.KING_SAFETY,evaluate.ATTACK_ACTIVITY,evaluate.INITIATIVE)
        b=Board();before=b.snapshot()
        report=evaluate.evaluation_breakdown(b,king_safety=True,attack_activity=True,initiative=True)
        self.assertIn('킹 안전',report['terms'])
        self.assertEqual(flags,(evaluate.KING_SAFETY,evaluate.ATTACK_ACTIVITY,evaluate.INITIATIVE))
        self.assertEqual(before,b.snapshot());self.assertIsNone(report['search_score'])

    def test_dead_material_override_is_explained(self):
        b=Board('7k/8/8/8/8/8/8/KB6 w - - 0 1')
        report=evaluate.evaluation_breakdown(b)
        self.assertTrue(report['dead_position']);self.assertEqual(report['static_score'],0)
        self.assertNotEqual(report['rounded_before_override'],0)

    def test_evaluation_switch_invalidates_warm_tt(self):
        b=Board('r1bqk2r/pppp1ppp/2n2n2/2b1p3/4P3/2NP1N2/PPP2PPP/R1BQKB1R w KQkq - 2 5')
        saved=evaluate.ATTACK_ACTIVITY
        try:
            warm=Searcher();warm.set_tactical(True)
            evaluate.ATTACK_ACTIVITY=False
            warm.search(b,max_depth=3,on_info=None)
            evaluate.ATTACK_ACTIVITY=True
            a=warm.search(b,max_depth=3,on_info=None)
            fresh=Searcher();fresh.set_tactical(True)
            c=fresh.search(b,max_depth=3,on_info=None)
            self.assertEqual(a,c)
            self.assertEqual(warm.nodes,fresh.nodes)
        finally:evaluate.ATTACK_ACTIVITY=saved

    def test_before_after_is_white_pov_and_snapshot_only(self):
        a=AnalysisSession(threading.Lock());a.set_fen('7k/8/8/8/8/8/p7/R6K w - - 0 1')
        before=a.board.snapshot()
        result=a.evaluation(dict(expected_fen=a.board.fen(),uci='a1a2'))
        self.assertEqual(result['delta'],result['after']['static_score']-result['before']['static_score'])
        self.assertEqual(result['after']['terms']['기물 가치']['mg']-result['before']['terms']['기물 가치']['mg'],100)
        self.assertEqual(before,a.board.snapshot())
        for obj in ({'expected_fen':'old'}, {'expected_fen':a.board.fen(),'uci':'h1h8'},
                    {'expected_fen':a.board.fen(),'uci':0},
                    {'expected_fen':a.board.fen(),'options':{'king_safety':'true'}}):
            with self.assertRaises(ValueError):a.evaluation(obj)

    def test_http_evaluation_route(self):
        from web_server import make_server
        server=make_server(0);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        try:
            req=Request(f'http://127.0.0.1:{server.server_port}/api/analysis/evaluation',
                data=json.dumps(dict(expected_fen=Board().fen(),uci='e2e4')).encode(),
                headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=5) as r:result=json.load(r)
            self.assertEqual(result['before']['kind'],'static')
            self.assertEqual(result['after']['fen'].split()[1],'b')
        finally:server.shutdown();server.server_close();t.join()


class ResearchTests(unittest.TestCase):
    def test_features_mirror_and_zero_weights(self):
        rng=random.Random(94);b=Board()
        for _ in range(80):
            moves=b.legal_moves()
            if not moves:break
            b.make_move(rng.choice(moves))
            self.assertEqual(features(b),[-x for x in features(evaluate.mirror(b))])
            self.assertEqual(score_white(b,(0,)*13),evaluate.evaluate_white(b))
            self.assertEqual(score_white(b,INITIAL),-score_white(evaluate.mirror(b),INITIAL))

    def test_research_override_restores_on_error(self):
        import search
        original=search.evaluate
        with self.assertRaisesRegex(RuntimeError,'test'):
            with candidate(INITIAL):
                self.assertIsNot(search.evaluate,original)
                raise RuntimeError('test')
        self.assertIs(search.evaluate,original)

    def test_trace_does_not_change_search_and_includes_reasons(self):
        fen='r3k2r/ppp2ppp/2n1bn2/3qp3/8/2N1PN2/PPP2PPP/R2QKB1R w KQkq - 0 1'
        results=[];events=[]
        for enabled in (False,True):
            s=Searcher();s.set_tactical(True);b=Board(fen);snap=b.snapshot()
            if enabled:
                trace=PruningTrace(s,10000);s.selective_trace=trace
            move,score=s.search(b,max_depth=4,on_info=None)
            results.append((move,score,s.nodes));self.assertEqual(snap,b.snapshot())
            if enabled:events=trace.events
        self.assertEqual(results[0],results[1])
        records=[e for e in events if e['reason'] in ('lmp','futility','lmr')]
        self.assertTrue(records)
        for e in records:
            self.assertIn('history_score',e);self.assertIn('killer',e)
            self.assertIsNotNone(Board(e['fen']).parse_uci(e['move']))

    def test_game_split_and_canonical_ep(self):
        from research.texel_v094 import split_game,key
        self.assertEqual(split_game('game',9417),split_game('game',9417))
        self.assertEqual(key('8/8/8/8/P7/8/4K3/7k b - a3 0 1'),
                         key('8/8/8/8/P7/8/4K3/7k b - - 12 20'))

    def test_supplied_games_legality(self):
        from research.diagnostics_v094 import replay
        games,cases=replay('research/data/user_games_v094.pgn')
        self.assertEqual([g['plies'] for g in games],[50,104])
        self.assertFalse(games[0]['checkmate']);self.assertTrue(games[1]['checkmate'])
        self.assertEqual(len(cases),21)


if __name__=='__main__':unittest.main()
