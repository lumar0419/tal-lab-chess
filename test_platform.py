import json
import threading
import time
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from board import Board, START_FEN
from notation import san_for_move
from analysis_server import AnalysisSession
from pgn_io import parse_pgn
from sacrifice import candidate_evidence, exchange_gain, analyze_candidate

class PGNTests(unittest.TestCase):
    def test_annotations_variations(self):
        p=parse_pgn('[White "A"]\n1.e4 {main} e5 (1...c5 (2.Nf3)) 2.Nf3 $1 Nc6 ; note\n3.Bb5 a6 *')
        self.assertEqual([m['uci'] for m in p['moves']],['e2e4','e7e5','g1f3','b8c6','f1b5','a7a6'])
        self.assertEqual(p['tags']['White'],'A')
    def test_castle_and_promotion(self):
        p=parse_pgn('1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.0-0 *');self.assertEqual(p['moves'][-1]['uci'],'e1g1')
        p=parse_pgn('[SetUp "1"] [FEN "7k/P7/8/8/8/8/8/7K w - - 0 1"] 1.a8=N *')
        self.assertEqual(p['moves'][0]['uci'],'a7a8n')
    def test_black_start_ep(self):
        p=parse_pgn('[FEN "7k/8/8/8/3p4/8/4P3/7K w - - 0 1"] 1.e4 dxe3 *')
        self.assertEqual(p['moves'][1]['uci'],'d4e3')
        p=parse_pgn('[FEN "7k/8/8/8/8/8/P7/7K b - - 0 12"] 12...Kg8 *')
        self.assertEqual(p['moves'][0]['uci'],'h8g8')
    def test_reject_bad_input(self):
        for text in ['1.e5 *','1.e4 (e5','1.e4 )','1.e4 {oops','1.e4 * 1.d4 *','[SetUp "1"] *','[Variant "Atomic"] *','x'*131073]:
            with self.subTest(text=text[:25]),self.assertRaises(ValueError):parse_pgn(text)
    def test_navigation_preserves_repetition_branch_and_atomicity(self):
        a=AnalysisSession(threading.Lock(),san_for_move=san_for_move)
        a.import_pgn('1.Nf3 Nf6 2.Ng1 Ng8 3.Nf3 Nf6 4.Ng1 Ng8 *')
        a.navigate(8);self.assertTrue(a.board.claimable_draw())
        original=a.state()
        with self.assertRaises(ValueError):a.import_pgn('1.e5 *')
        self.assertEqual(a.state(),original)
        a.navigate(2);a.move('e2e4');self.assertEqual(len(a.state()['game_moves']),3)
        a.undo();a.navigate(3);self.assertEqual(a.state()['moves'][-1]['uci'],'e2e4')
    def test_sync_session_progress(self):
        updates=[]
        a=AnalysisSession(threading.Lock(),san_for_move=san_for_move,background=False,on_update=updates.append)
        a.start({'min_depth':2,'max_depth':2,'seconds':2,'multipv':3})
        self.assertEqual([s['completed']['depth'] for s in updates],[1,2])
        self.assertFalse(a.state()['active'])
        self.assertEqual(a.state()['game_scores'][0]['depth'],2)

class SacrificeTests(unittest.TestCase):
    def test_losing_offer_and_equal_exchange(self):
        b=Board('7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1')
        original=b.snapshot();e=candidate_evidence(b,'e2e4');self.assertIsNotNone(e)
        self.assertIn('d5e4',[m['uci'] for m in e['acceptances']]);self.assertEqual(b.snapshot(),original)
        b=Board('4k3/8/8/3p4/2B5/8/8/4K3 w - - 0 1')
        self.assertIsNone(candidate_evidence(b,'c4d5'))
    def test_pinned_acceptance_not_counted(self):
        b=Board('4k3/4p3/8/8/8/8/3Q4/K3R3 w - - 0 1')
        self.assertIsNone(candidate_evidence(b,'d2d6'))
    def test_best_defense_is_legal_and_no_score_bonus(self):
        b=Board('7k/8/8/3p4/8/8/4Q3/4K3 w - - 0 1');before=b.snapshot()
        r=analyze_candidate(b,'e2e4',depth=2,seconds=2)
        self.assertEqual(b.snapshot(),before);self.assertGreater(r['depth'],0)
        for uci in r['pv']:
            move=b.parse_uci(uci);self.assertIsNotNone(move);b.make_move(move)
        self.assertNotIn('brilliant',r['status'])

class PlatformHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web_server import make_server
        cls.server=make_server(0);cls.t=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.t.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.t.join()
    def post(self,path,obj):
        with urlopen(Request(self.base+path,data=json.dumps(obj).encode(),headers={'Content-Type':'application/json'})) as r:return json.loads(r.read())
    def test_import_navigate_and_engine_allowlist(self):
        s=self.post('/api/analysis/pgn',{'pgn':'1.e4 e5 2.Nf3 *'});self.assertEqual(s['cursor'],0)
        s=self.post('/api/analysis/navigate',{'ply':3});self.assertEqual(s['moves'][-1]['uci'],'g1f3')
        with urlopen(self.base+'/engine/board.py') as r:self.assertIn(b'class Board',r.read())
        for path in ['/engine/cloud_server.py','/engine/../cloud_server.py','/engine/.git/config']:
            with self.assertRaises(HTTPError) as cm:urlopen(self.base+path)
            self.assertEqual(cm.exception.code,404)
    def test_benchmark(self):
        r=self.post('/api/analysis/benchmark',{});self.assertEqual(len(r['samples']),3)
        self.assertGreater(r['median_nps'],0)
        self.assertEqual(r['samples'][0]['results'],r['samples'][2]['results'])

if __name__=='__main__':unittest.main(verbosity=2)
