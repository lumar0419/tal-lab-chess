"""Regression tests for Tal Lab local web UI (no third-party dependencies)."""
import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from board import BLACK, WHITE, Board
from web_server import Game, make_server, san_for_move


class SanTests(unittest.TestCase):
    def test_standard_and_opening(self):
        b = Board()
        self.assertEqual(san_for_move(b, b.parse_uci('e2e4')), 'e4')
        b.push_uci('e2e4')
        self.assertEqual(san_for_move(b, b.parse_uci('e7e5')), 'e5')
        b.push_uci('e7e5')
        self.assertEqual(san_for_move(b, b.parse_uci('g1f3')), 'Nf3')

    def test_castling_and_checks(self):
        b = Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1')
        self.assertEqual(san_for_move(b, b.parse_uci('e1g1')), 'O-O')
        self.assertEqual(san_for_move(b, b.parse_uci('e1c1')), 'O-O-O')
        b = Board('7k/8/6K1/8/8/8/8/R7 w - - 0 1')
        self.assertEqual(san_for_move(b, b.parse_uci('a1a8')), 'Ra8#')

    def test_promotion(self):
        b = Board('7k/5P2/6K1/8/8/8/8/8 w - - 0 1')
        self.assertEqual(san_for_move(b, b.parse_uci('f7f8q')), 'f8=Q#')

    def test_ep(self):
        b = Board('7k/8/8/3pP3/8/8/8/4K3 w - d6 0 1')
        self.assertEqual(san_for_move(b, b.parse_uci('e5d6')), 'exd6')

    def test_disambiguation_file(self):
        b = Board('6k1/8/8/8/8/8/4K3/R6R w - - 0 1')
        self.assertEqual(san_for_move(b, b.parse_uci('a1d1')), 'Rad1')


class GameTests(unittest.TestCase):
    def setUp(self):
        self.game = Game()

    def test_user_move_undo_and_pgn(self):
        self.assertIn('e2e4', self.game.state()['legal'])
        state = self.game.move('e2e4')
        self.assertEqual(state['moves'][0]['san'], 'e4')
        undone = self.game.undo()
        self.assertFalse(undone['moves'])
        self.assertEqual(undone['side_to_move'], 'white')
        self.assertEqual(undone['fen'], Board().fen())
        self.assertTrue(self.game.pgn().endswith('*\n'))

    def test_reject_illegal_and_wrong_turn(self):
        for m in ['e2e5','e2e4q','bad','a2a2',42]:
            with self.assertRaises(ValueError): self.game.move(m)
        self.game.move('d2d4')
        with self.assertRaises(ValueError): self.game.move('e2e4')

    def test_pgn_save(self):
        self.game.move('e2e4')
        self.assertIn('1. e4', self.game.pgn())
        self.assertIn('[Result "*"]',self.game.pgn())
        self.game.resign()
        self.assertIn('[Result "0-1"]',self.game.pgn())

    def test_options_validation(self):
        for obj in ({'depth':999}, {'seconds':0}, {'options':{'hack':True}},
                    {'options':{'initiative':'false'}}, {'side':'red'}, {'depth':True}):
            with self.assertRaises(ValueError):self.game.new(obj)
        s=self.game.new({'side':'white','depth':3,'seconds':0.2,
                         'options':{'tactical_checks':True,'initiative':True}})
        self.assertTrue(s['options']['initiative'])
        self.assertFalse(s['options']['attack_activity'])

    def test_black_engine_plays_first(self):
        self.game.new({'side':'black','depth':1,'seconds':0.12})
        end=time.time()+10
        while time.time()<end and self.game.state()['thinking']:
            time.sleep(.04)
        state=self.game.state()
        self.assertFalse(state['thinking'])
        self.assertIsNone(state['error'])
        self.assertEqual(len(state['moves']),1)
        self.assertEqual(state['side_to_move'],'black')
        self.assertTrue(state['legal'])

    def test_white_player_receives_legal_reply(self):
        self.game.new({'side':'white','depth':1,'seconds':0.1})
        self.game.move('e2e4')
        end=time.time()+10
        while time.time()<end and self.game.state()['thinking']:
            time.sleep(.03)
        state=self.game.state()
        self.assertFalse(state['thinking'])
        self.assertIsNone(state['error'])
        self.assertEqual(len(state['moves']),2)
        self.assertEqual(state['side_to_move'],'white')
        self.assertEqual(state['moves'][0]['san'],'e4')
        self.assertTrue(state['legal'])
        self.assertIn('1. e4',self.game.pgn())

    def test_undo_pending_engine_and_ignore_old_result(self):
        self.game.new({'side':'white','depth':6,'seconds':2.5})
        self.game.move('e2e4')
        self.game.undo()
        self.assertEqual(self.game.state()['fen'],Board().fen())
        # cancel during search must not reinsert an old engine move
        time.sleep(.2)
        self.assertFalse(self.game.state()['moves'])

    def test_claim_draw_requires_condition(self):
        with self.assertRaises(ValueError): self.game.draw()


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0, game=Game())
        cls.host='http://127.0.0.1:%d'%cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, route, headers=None):
        with urlopen(Request(self.host+route, headers=headers or {}),timeout=3) as r:
            return r.status,r.headers,r.read()

    def post(self, route, data):
        raw=json.dumps(data).encode()
        return self.get_body(Request(self.host+route,data=raw,
                 headers={'Content-Type':'application/json'},method='POST'))

    def get_body(self, req):
        try:
            with urlopen(req,timeout=3) as resp:
                return resp.status,json.load(resp)
        except HTTPError as err:
            return err.code,json.load(err)

    def test_html_js_css(self):
        for path,contents in (('/',b'TAL'),('/app.js',b'onSquare'),('/styles.css',b'chessboard'),
                              ('/favicon.svg',b'<svg')):
            code,headers,data=self.get(path)
            self.assertEqual(code,200)
            self.assertIn(contents,data)
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')

    def test_api_complete(self):
        status,data=self.post('/api/new',{'side':'white','depth':1,'seconds':.1})
        self.assertEqual(status,200)
        self.assertIn('g1f3',data['legal'])
        status,data=self.post('/api/move',{'uci':'e2e5'})
        self.assertEqual(status,400)
        status,data=self.post('/api/move',{'uci':'e2e4'})
        self.assertEqual(status,200)
        self.assertTrue(data['thinking'])
        status,data=self.post('/api/undo',{})
        self.assertEqual(status,200)
        self.assertEqual(data['fen'],Board().fen())
        status,headers,pgn=self.get('/api/pgn')
        self.assertEqual(status,200)
        self.assertIn(b'[Event "Tal Lab Local Game"]',pgn)

    def test_host_protection(self):
        req=Request(self.host+'/api/state',headers={'Host':'example.com'})
        status,data=self.get_body(req)
        self.assertEqual(status,403)
        status,data=self.get_body(Request(self.host+'/api/new',data=b'{}',
                 headers={'Origin':'https://evil.example','Content-Type':'application/json'},method='POST'))
        self.assertEqual(status,403)


if __name__ == '__main__':
    unittest.main(verbosity=2)
