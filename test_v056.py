"""v0.5.6: MultiPV root search, complete-depth publishing and HTTP support."""
import threading
import time
import unittest
import json
from urllib.request import Request, urlopen

from version import VERSION
from board import Board
from search import Searcher, TimeUp
from analysis_server import AnalysisSession
from web_server import san_for_move


class MultiPVSearchTests(unittest.TestCase):
    def test_legal_unique_sorted_root_lines(self):
        b = Board()
        original = b.snapshot()
        snapshots = []
        moves = {m.uci() for m in b.legal_moves()}
        searcher = Searcher(tt_size=12_000)
        best, score = searcher.search(b, max_depth=3, multipv=3, on_info=None,
                                      on_multipv=lambda lines: snapshots.append(lines))
        self.assertEqual(len(snapshots), 3)
        self.assertEqual([lines[0].depth for lines in snapshots], [1, 2, 3])
        for lines in snapshots:
            self.assertEqual(len(lines), 3)
            self.assertEqual(len(set(l.pv[0].uci() for l in lines)), 3)
            self.assertTrue(all(l.pv[0].uci() in moves for l in lines))
            self.assertEqual([l.score for l in lines], sorted((l.score for l in lines), reverse=True))
        self.assertEqual(best.uci(), snapshots[-1][0].pv[0].uci())
        self.assertEqual(score, snapshots[-1][0].score)
        self.assertEqual(b.snapshot(), original)

    def test_forced_root_scores_match_independent_single_line(self):
        fen = 'r3k2r/p1ppqpb1/bn2pnp1/2pP4/1p2P3/2N2N2/PPQBBPPP/R3K2R w KQkq - 0 1'
        board = Board(fen)
        data = []
        Searcher(tt_size=40_000).search(board, max_depth=3, multipv=3, on_info=None,
                                        on_multipv=lambda lines: data.append(lines))
        for line in data[-1]:
            move = line.pv[0].uci()
            s = Searcher(tt_size=40_000)
            chosen, score = s.search(board, max_depth=3, root_moves=[move], on_info=None)
            self.assertEqual(move, chosen.uci())
            self.assertEqual(score, line.score, move)

    def test_no_partial_depth_publish(self):
        class StopAfterFirstRankAtDepthTwo(Searcher):
            root_calls = 0
            def negamax(self, *args, **kwargs):
                if len(args) >= 5 and args[4] == 0:
                    self.root_calls += 1
                    if self.root_calls == 5:
                        raise TimeUp()
                return super().negamax(*args, **kwargs)
        b = Board()
        previous = b.fen()
        seen=[]
        searcher = StopAfterFirstRankAtDepthTwo(tt_size=4096)
        m, score = searcher.search(b, max_depth=4, multipv=3, on_info=None,
                                   on_multipv=lambda lines:seen.append(lines))
        self.assertEqual([r[0].depth for r in seen], [1])
        self.assertEqual(len(seen[0]), 3)
        self.assertEqual(m.uci(), seen[0][0].pv[0].uci())
        self.assertEqual(score, seen[0][0].score)
        self.assertEqual(b.fen(), previous)

    def test_single_pv_compatibility_and_parameter_validation(self):
        b=Board()
        for n in (0, 6, True, 1.3, '3'):
            with self.assertRaises(ValueError):
                Searcher().search(b, max_depth=2, multipv=n, on_info=None)
        normal=Searcher(tt_size=10_000).search(b,max_depth=3,on_info=None)
        one=Searcher(tt_size=10_000).search(b,max_depth=3,multipv=1,on_info=None)
        self.assertEqual((normal[0].uci(),normal[1]), (one[0].uci(),one[1]))


class MultiPVSessionTests(unittest.TestCase):
    def setUp(self):
        self.a = AnalysisSession(threading.Lock(), search_wait_seconds=3, san_for_move=san_for_move)
    def tearDown(self):
        self.a.stop()
    def _wait(self):
        end = time.monotonic()+8
        while time.monotonic()<end:
            state = self.a.state()
            if not state['active']:return state
            time.sleep(.02)
        self.fail('timeout')
    def test_default_and_three_lines_with_valid_san(self):
        self.assertEqual(self.a.state()['multipv'], 3)
        self.a.start({'min_depth':2,'max_depth':3,'seconds':5,'multipv':3})
        s=self._wait()
        self.assertEqual(s['status'],'completed')
        self.assertEqual(s['completed']['depth'],3)
        self.assertEqual(len(s['completed']['candidates']),3)
        for line in s['completed']['candidates']:
            self.assertEqual(line['rank'],s['completed']['candidates'].index(line)+1)
            self.assertEqual(line['depth'],3)
            self.assertTrue(line['pv'])
            self.assertTrue(line['pv_san'])
        self.assertEqual(self.a.state()['fen'], Board().fen())
    def test_one_line_and_black_score_perspective(self):
        self.a.move('e2e4')
        self.a.start({'min_depth':2,'max_depth':2,'seconds':5,'multipv':1})
        s=self._wait()
        self.assertEqual(s['side_to_move'],'black')
        self.assertEqual(len(s['completed']['candidates']),1)
        self.assertEqual(s['completed']['score'],s['completed']['candidates'][0]['score'])
        self.assertEqual(s['completed']['depth'],2)
    def test_invalid_count_rejected(self):
        for count in [0, 6, False, 2.4, '3']:
            with self.assertRaises(ValueError):self.a.start({'multipv':count})


class MultiPVHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from web_server import Game, make_server
        cls.http = make_server(0, Game())
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.http.server_port

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=2)

    def post(self, path, payload):
        req = Request(self.base + path, data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_http_candidate_list_and_UI(self):
        fresh = self.post('/api/analysis/reset', {})
        self.assertEqual(fresh['version'], VERSION)
        started = self.post('/api/analysis/start',
                            {'min_depth': 2, 'max_depth': 3, 'multipv': 3, 'seconds': 5})
        self.assertEqual(started['multipv'], 3)
        stop_at = time.monotonic() + 7
        while time.monotonic() < stop_at:
            with urlopen(self.base + '/api/analysis/state', timeout=5) as r:
                s = json.loads(r.read())
            if not s['active']:
                break
            time.sleep(.03)
        self.assertEqual(s['completed']['depth'], 3)
        self.assertEqual(len(s['completed']['candidates']), 3)
        for filename, needle in [('/analysis.js', b'renderCandidates'),
                                  ('/analysis', b'id="multipv"'),
                                  ('/analysis.css', b'multipv-card')]:
            with urlopen(self.base + filename, timeout=5) as r:
                self.assertIn(needle, r.read())


if __name__=='__main__': unittest.main(verbosity=2)
