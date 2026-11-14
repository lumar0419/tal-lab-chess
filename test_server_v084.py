import base64
from contextlib import closing
import http.client
import threading
import time
import unittest

import evaluate
from cloud_server import AuthLimiter, make_cloud_server
from search_gate import AUTO, GAME, MANUAL, SearchGate
from web_server import Game


def wait_until(predicate, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.01)
    return predicate()


class SearchAdmissionTests(unittest.TestCase):
    def test_game_preempts_automatic_analysis_across_sessions(self):
        first, second = Game(), Game()
        second.search_gate = first.search_gate
        first.search_wait_seconds = second.search_wait_seconds = 2
        analysis = first.analysis()
        state = analysis.state()
        analysis.start({'expected_fen': state['fen'], 'expected_epoch': state['epoch'],
                        'min_depth': 5, 'max_depth': 10, 'seconds': 30,
                        'options': {'king_safety': True, 'attack_activity': True}},
                       mode='auto')
        self.addCleanup(analysis.stop)
        self.assertTrue(wait_until(lambda: analysis.state()['completed'] is not None))
        before = analysis.state()
        second.new({'side': 'black', 'depth': 1, 'seconds': .1,
                    'options': {'initiative': True}})
        self.assertTrue(wait_until(lambda: not second.state()['thinking']))
        self.assertIsNone(second.state()['error'])
        self.assertEqual(len(second.state()['moves']), 1)
        after = analysis.state()
        self.assertEqual(after['status'], 'preempted')
        self.assertGreaterEqual(after['completed']['depth'], before['completed']['depth'])
        self.assertEqual(after['fen'], before['fen'])
        self.assertTrue(first.search_gate.acquire(blocking=False))
        first.search_gate.release()
        self.assertFalse(evaluate.KING_SAFETY)
        self.assertFalse(evaluate.ATTACK_ACTIVITY)
        self.assertFalse(evaluate.INITIATIVE)

    def test_manual_is_not_preempted_and_queue_is_bounded(self):
        gate = SearchGate(max_waiters=1)
        interrupted = threading.Event()
        self.assertTrue(gate.acquire_job(MANUAL, interrupted, lambda: False, 0))
        try:
            self.assertFalse(gate.acquire_job(GAME, threading.Event(), lambda: False, .03))
            self.assertFalse(interrupted.is_set())
            result = []
            cancelled = threading.Event()
            worker = threading.Thread(target=lambda: result.append(
                gate.acquire_job(AUTO, threading.Event(), cancelled.is_set, 1)), daemon=True)
            worker.start()
            self.assertTrue(wait_until(lambda: len(gate._waiters) == 1))
            self.assertFalse(gate.acquire_job(GAME, threading.Event(), lambda: False, 0))
            cancelled.set()
            worker.join(1)
            self.assertEqual(result, [False])
        finally:
            gate.release()

    def test_queued_stale_auto_is_discarded_on_position_change(self):
        game = Game()
        a = game.analysis()
        gate = game.search_gate
        self.assertTrue(gate.acquire())
        try:
            state = a.state()
            a.start({'expected_fen': state['fen'], 'expected_epoch': state['epoch']},
                    mode='auto')
            self.assertTrue(wait_until(lambda: len(gate._waiters) == 1))
            latest = a.move('e2e4')
            self.assertTrue(wait_until(lambda: not gate._waiters))
            stale = a.start({'expected_fen': state['fen'], 'expected_epoch': state['epoch']},
                            mode='auto')
            self.assertEqual(stale['epoch'], latest['epoch'])
        finally:
            gate.release()
        a.start({'expected_fen': latest['fen'], 'expected_epoch': latest['epoch'],
                 'min_depth': 2, 'max_depth': 2, 'seconds': 1}, mode='auto')
        self.addCleanup(a.stop)
        self.assertTrue(wait_until(lambda: not a.state()['active']))
        final = a.state()
        self.assertEqual(final['fen'], latest['fen'])
        self.assertEqual(final['completed']['depth'], 2)


class LoginIsolationTests(unittest.TestCase):
    def make_server(self, *trusted):
        server = make_cloud_server(0, host='127.0.0.1', public_host='127.0.0.1',
                                   auth_user='player', auth_password='test-credentials-084',
                                   secure=False, trusted_proxies=trusted)
        server.auth_limiter = AuthLimiter(max_failures=2, global_failures=4)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def request(self, server, password=None, forwarded=None, cookie=None):
        headers = {}
        if password is not None:
            headers['Authorization'] = 'Basic ' + base64.b64encode(f'player:{password}'.encode()).decode()
        if forwarded is not None:
            headers['X-Forwarded-For'] = forwarded
        if cookie is not None:
            headers['Cookie'] = cookie
        with closing(http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)) as connection:
            connection.request('GET', '/api/state', headers=headers)
            response = connection.getresponse()
            response.read()
            return response.status, response.getheader('Set-Cookie')

    def test_untrusted_forwarding_cannot_change_limit_and_active_session_survives(self):
        server = self.make_server()
        good = 'test-credentials-084'
        status, cookie = self.request(server, good)
        self.assertEqual(status, 200)
        cookie = cookie.split(';', 1)[0]
        for address in ('192.0.2.1', '192.0.2.2'):
            self.assertEqual(self.request(server, 'wrong', address)[0], 401)
        self.assertEqual(self.request(server, 'wrong', '192.0.2.3')[0], 429)
        self.assertEqual(self.request(server, good, '192.0.2.3')[0], 429)
        self.assertEqual(self.request(server, 'wrong', '192.0.2.3', cookie)[0], 429)
        self.assertEqual(self.request(server, good, '192.0.2.3', cookie)[0], 200)

    def test_trusted_hops_isolate_clients_and_global_limit_protects_fresh_logins(self):
        server = self.make_server('127.0.0.1/32', '10.1.0.0/24')
        good = 'test-credentials-084'
        for prefix in ('198.51.100.7', '198.51.100.8'):
            self.assertEqual(self.request(server, 'wrong', prefix + ', 192.0.2.1, 10.1.0.2')[0], 401)
        self.assertEqual(self.request(server, 'wrong', '192.0.2.1, 10.1.0.2')[0], 429)
        self.assertEqual(self.request(server, good, '192.0.2.2, 10.1.0.2')[0], 200)
        self.assertEqual(self.request(server, 'wrong', '192.0.2.2, 10.1.0.2')[0], 401)
        self.assertEqual(self.request(server, 'wrong', '192.0.2.3, 10.1.0.2')[0], 401)
        self.assertEqual(self.request(server, 'wrong', '192.0.2.4, 10.1.0.2')[0], 429)
        self.assertEqual(self.request(server, good, '192.0.2.4, 10.1.0.2')[0], 429)
