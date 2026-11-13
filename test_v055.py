"""Tal Lab v0.5.5: automatic analysis lifecycle and API regressions."""
import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from analysis_server import AnalysisSession
from board import Board
from web_server import Game, make_server


def options(fen, minimum=2, maximum=3, seconds=5):
    return {'expected_fen': fen, 'min_depth': minimum, 'max_depth': maximum,
            'seconds': seconds, 'options': {}}


def wait_done(a, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = a.state()
        if not s['active']:
            return s
        time.sleep(.02)
    raise AssertionError('Analysis did not complete within test deadline')


class AutomaticAnalysisSessionTests(unittest.TestCase):
    def setUp(self):
        self.a = AnalysisSession(threading.Lock(), search_wait_seconds=3)

    def tearDown(self):
        self.a.stop()

    def test_auto_starts_idle_and_finishes(self):
        fen = self.a.state()['fen']
        self.assertTrue(self.a.start(options(fen), mode='auto')['active'])
        state = wait_done(self.a)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['completed']['depth'], 3)
        self.assertEqual(len(state['iterations']), 3)
        self.assertEqual(state['fen'], fen)

    def test_auto_is_idempotent_while_running_and_after_finish(self):
        fen = self.a.state()['fen']
        self.a.start(options(fen, 5, 7, 10), mode='auto')
        epoch = self.a.epoch
        self.a.start(options(fen, 5, 7, 10), mode='auto')
        self.assertEqual(self.a.epoch, epoch)
        self.a.stop()
        stopped_epoch = self.a.epoch
        self.a.start(options(fen), mode='auto')
        self.assertEqual(self.a.epoch, stopped_epoch)
        self.assertEqual(self.a.state()['status'], 'stopped')

    def test_auto_does_not_restart_completed_position(self):
        fen = self.a.state()['fen']
        self.a.start(options(fen), mode='auto')
        finished = wait_done(self.a)
        old_epoch = self.a.epoch
        self.a.start(options(fen), mode='auto')
        self.assertEqual(self.a.epoch, old_epoch)
        self.assertEqual(self.a.state()['iterations'], finished['iterations'])

    def test_stale_fen_cannot_start_or_interrupt_current_search(self):
        old_fen = self.a.state()['fen']
        self.a.move('e2e4')
        new_fen = self.a.state()['fen']
        before = self.a.epoch
        for mode in ('auto', 'restart'):
            s = self.a.start(options(old_fen), mode=mode)
            self.assertEqual(s['fen'], new_fen)
            self.assertFalse(s['active'])
            self.assertEqual(self.a.epoch, before)
        self.a.start(options(new_fen,2,4), mode='auto')
        new_epoch = self.a.epoch
        self.a.start(options(old_fen), mode='restart')
        self.assertEqual(self.a.epoch, new_epoch)

    def test_change_position_cancels_old_search_and_can_autostart(self):
        old_fen = self.a.state()['fen']
        self.a.start(options(old_fen,6,10,10),mode='auto')
        self.a.move('e2e4')
        s=self.a.state()
        self.assertEqual(s['status'],'idle')
        self.assertFalse(s['active'])
        self.assertEqual(s['iterations'],[])
        self.a.start(options(s['fen']),mode='auto')
        self.assertEqual(wait_done(self.a)['completed']['depth'],3)

    def test_restart_replaces_running_search(self):
        fen = self.a.state()['fen']
        self.a.start(options(fen,6,10,10),mode='auto')
        before = self.a.epoch
        new = self.a.start(options(fen,2,3,5),mode='restart')
        self.assertTrue(new['active'])
        self.assertGreater(self.a.epoch,before)
        done = wait_done(self.a)
        self.assertEqual(done['status'],'completed')
        self.assertEqual(done['completed']['depth'],3)

    def test_no_auto_search_of_terminal_positions(self):
        self.a.set_fen('7k/6Q1/5K2/8/8/8/8/8 b - - 0 1')
        fen=self.a.state()['fen']
        s=self.a.start(options(fen),mode='auto')
        self.assertFalse(s['active'])
        self.assertEqual(s['status'],'idle')

    def test_rejects_missing_expected_fen_and_invalid_config(self):
        with self.assertRaises(ValueError): self.a.start({'min_depth':2,'max_depth':3,'seconds':5},mode='auto')
        with self.assertRaises(ValueError): self.a.start(options(self.a.state()['fen']),mode='oops')


class AutomaticAnalysisHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0,Game())
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        cls.t=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.t.join(timeout=2)

    def post(self,path,data):
        req=Request(self.base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=8) as response:
            return json.loads(response.read())

    def test_browser_can_autostart_then_change_settings(self):
        fen=self.post('/api/analysis/reset',{})['fen']
        self.assertTrue(self.post('/api/analysis/auto',options(fen))['active'])
        new=self.post('/api/analysis/restart',options(fen,2,4))
        self.assertEqual(new['max_depth'],4)
        end=time.monotonic()+8
        while new['active'] and time.monotonic()<end:
            time.sleep(.02)
            with urlopen(self.base+'/api/analysis/state',timeout=5) as r:new=json.loads(r.read())
        self.assertEqual(new['completed']['depth'],4)
        self.assertEqual(new['status'],'completed')

    def test_routes_and_client_source_are_exposed(self):
        for path,needle in [('/',b'id="auto-analyze"'),('/analysis.js',b'scheduleAuto'),
                            ('/analysis.css',b'auto-analysis-setting')]:
            with urlopen(self.base+path,timeout=5) as r:
                self.assertEqual(r.status,200)
                self.assertIn(needle,r.read())


if __name__ == '__main__': unittest.main(verbosity=2)
