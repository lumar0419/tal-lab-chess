"""v0.5.4: position analysis, progressive search and HTTP compatibility."""
import json
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from board import Board, START_FEN
from search import Searcher
from web_server import Game, make_server


class SearchDepthTests(unittest.TestCase):
    def test_report_each_completed_depth(self):
        started, completed = [], []
        board = Board()
        fen = board.fen()
        Searcher(tt_size=2048).search(board, max_depth=4, min_depth=4,
               time_limit=10, on_iteration=started.append, on_info=completed.append)
        self.assertEqual(started, [1,2,3,4])
        self.assertEqual([r.depth for r in completed], [1,2,3,4])
        self.assertEqual(board.fen(),fen)

    def test_invalid_minimum(self):
        for minimum in [0,3, True, '4']:
            with self.assertRaises(ValueError):
                Searcher().search(Board(),max_depth=2,min_depth=minimum,on_info=None)

    def test_old_search_signature_works(self):
        board = Board()
        m,_ = Searcher(tt_size=2048).search(board,max_depth=2,time_limit=5,on_info=None)
        self.assertIn(m.uci(), [x.uci() for x in board.legal_moves()])


class AnalysisStateTests(unittest.TestCase):
    def setUp(self):
        self.game=Game()
        self.a=self.game.analysis()

    def test_can_make_both_sides_and_undo(self):
        self.a.move('e2e4')
        self.assertEqual(self.a.state()['side_to_move'],'black')
        self.a.move('e7e5')
        self.assertEqual(len(self.a.state()['moves']),2)
        self.a.undo()
        self.assertEqual(self.a.state()['side_to_move'],'black')
        self.a.reset()
        self.assertEqual(self.a.state()['fen'],Board().fen())
        self.assertFalse(self.a.state()['moves'])

    def test_load_historical_position_and_reject_illegal(self):
        fen='r2q1rk1/pp2ppbp/1np2np1/2Q3B1/3PP1b1/2N2N2/PP3PPP/3RKB1R b K - 6 11'
        self.assertEqual(self.a.set_fen(fen)['fen'],fen)
        self.assertIn('b6a4',self.a.state()['legal'])
        with self.assertRaises(ValueError): self.a.move('b6h6')
        with self.assertRaises(ValueError): self.a.set_fen('invalid')
        self.assertEqual(self.a.state()['fen'],fen)

    def test_depth_options_validation(self):
        for config in [
            {'min_depth':9,'max_depth':8}, {'min_depth':4,'max_depth':11},
            {'min_depth':1,'max_depth':3,'seconds':100},
            {'min_depth':True,'max_depth':5},
            {'min_depth':3,'max_depth':4,'options':{'lmr':'true'}},
        ]:
            with self.assertRaises(ValueError):self.a.start(config)

    def test_progress_and_stop(self):
        self.a.start({'min_depth':2,'max_depth':4,'seconds':10})
        end=time.monotonic()+10
        seen=set()
        while time.monotonic()<end:
            s=self.a.state()
            if s['completed']:seen.add(s['completed']['depth'])
            if not s['active']:break
            time.sleep(.015)
        self.assertEqual(s['status'],'completed')
        self.assertEqual([x['depth'] for x in s['iterations']], [1,2,3,4])
        self.assertEqual(s['completed']['depth'],4)
        self.assertEqual(self.a.state()['fen'],Board().fen())

    def test_stopping_ignores_old_worker(self):
        self.a.start({'min_depth':6,'max_depth':10,'seconds':20})
        self.a.stop()
        state=self.a.move('e2e4')
        self.assertEqual(state['status'],'idle')
        time.sleep(.2)
        self.assertEqual(self.a.state()['fen'],state['fen'])
        self.assertEqual(self.a.state()['iterations'],[])


class AnalysisWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0,Game())
        cls.base='http://127.0.0.1:%d'%cls.server.server_port
        cls.t=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.t.join(timeout=2)

    def request(self,path,data=None):
        payload=json.dumps(data).encode() if data is not None else None
        req=Request(self.base+path,data=payload,headers={'Content-Type':'application/json'} if payload else {})
        try:
            with urlopen(req,timeout=8) as r:return r.status,r.read(),r.headers
        except HTTPError as exc:return exc.code,exc.read(),exc.headers

    def test_root_analysis_and_play_backward_compatibility(self):
        for path,expected in [('/',b'POSITION EXPLORER'),('/analysis',b'LIVE SEARCH'),
                              ('/analysis.js',b'renderIterations'),('/analysis.css',b'analysis-hero'),
                              ('/play',b'LIVE MATCH'),('/app.js',b'renderBoard')]:
            code,body,_=self.request(path)
            self.assertEqual(code,200,path)
            self.assertIn(expected,body,path)

    def test_state_and_master_cases(self):
        code,body,_=self.request('/api/analysis/state')
        self.assertEqual(code,200)
        self.assertIn('e2e4',json.loads(body)['legal'])
        code,body,_=self.request('/api/analysis/cases')
        self.assertEqual(code,200)
        self.assertGreater(len(json.loads(body)['positions']),2)

    def test_post_and_live_depth_results(self):
        code,body,_=self.request('/api/analysis/reset',{})
        self.assertEqual(code,200)
        code,body,_=self.request('/api/analysis/start',{'min_depth':2,'max_depth':3,'seconds':10})
        self.assertEqual(code,200)
        end=time.monotonic()+10
        while time.monotonic()<end:
            code,body,_=self.request('/api/analysis/state')
            data=json.loads(body)
            if not data['active']:break
            time.sleep(.05)
        self.assertEqual(data['status'],'completed')
        self.assertEqual(data['completed']['depth'],3)
        self.assertEqual([x['depth'] for x in data['iterations']],[1,2,3])




class CloudAnalysisHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cloud_server import make_cloud_server
        import base64
        cls.server=make_cloud_server(0,host='127.0.0.1', public_host='127.0.0.1',
                                     auth_user='player',auth_password='this-is-a-testing-password',secure=False)
        cls.base='http://127.0.0.1:%d'%cls.server.server_port
        cls.origin=cls.base
        cls.auth='Basic '+base64.b64encode(b'player:this-is-a-testing-password').decode()
        cls.t=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.t.join(timeout=2)

    def fetch(self,path,data=None,token=None):
        req=Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Authorization':self.auth,'Origin':self.origin,
                             'Content-Type':'application/json',
                             **({'Cookie':token} if token else {})})
        try:
            with urlopen(req,timeout=5) as res:
                return res.status,res.headers,res.read()
        except HTTPError as err:
            return err.code,err.headers,err.read()

    def test_cloud_state_and_start(self):
        status,headers,body=self.fetch('/api/analysis/state')
        self.assertEqual(status,200)
        cookie=headers.get('Set-Cookie').split(';')[0]
        self.assertTrue(cookie.startswith('tal_lab_sid='))
        status,_,body=self.fetch('/api/analysis/start',{'min_depth':2,'max_depth':3,'seconds':10},cookie)
        self.assertEqual(status,200)
        end=time.monotonic()+10
        while time.monotonic()<end:
            status,_,body=self.fetch('/api/analysis/state',token=cookie)
            data=json.loads(body)
            if not data['active']:break
            time.sleep(.08)
        self.assertEqual(data['status'],'completed')
        self.assertEqual(data['completed']['depth'],3)

    def test_auth_still_required(self):
        req=Request(self.base+'/api/analysis/state')
        with self.assertRaises(HTTPError) as x:urlopen(req,timeout=3)
        self.assertEqual(x.exception.code,401)

if __name__=='__main__':unittest.main(verbosity=2)
