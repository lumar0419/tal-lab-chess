"""v0.5.2 hosted-service hardening and Tal evaluation cache regression tests."""
import base64
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import evaluate
from board import Board
from cloud_server import AuthLimiter, Sessions, make_cloud_server
from web_server import Game


class FakeClock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_cloud_server(0, host='127.0.0.1', public_host='127.0.0.1',
                                       auth_user='player', auth_password='long_test_password_2026',
                                       secure=False)
        cls.root = f'http://127.0.0.1:{cls.server.server_port}'
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.good = 'Basic ' + base64.b64encode(b'player:long_test_password_2026').decode()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, method, path, authorization=None):
        headers = {}
        if authorization:
            headers['Authorization'] = authorization
        req = Request(self.root + path, method=method, headers=headers)
        try:
            with urlopen(req, timeout=3) as resp:
                return resp.status, resp.headers, resp.read()
        except HTTPError as err:
            return err.code, err.headers, err.read()

    def test_head_responds_without_body_or_session(self):
        status, headers, data = self.request('HEAD', '/healthz')
        self.assertEqual((status, data), (200, b''))
        self.assertEqual(headers['Content-Length'], '3')
        status, headers, data = self.request('HEAD', '/')
        self.assertEqual((status, data), (401, b''))
        status, headers, data = self.request('HEAD', '/', self.good)
        self.assertEqual((status, data), (200, b''))
        self.assertIsNone(headers.get('Set-Cookie'))
        status, headers, data = self.request('HEAD', '/api/state', self.good)
        self.assertEqual((status, data), (405, b''))

    def test_repeated_auth_failures_are_throttled(self):
        old = self.server.auth_limiter
        clock = FakeClock()
        self.server.auth_limiter = AuthLimiter(max_failures=3, window=60, penalty=90, clock=clock)
        wrong = 'Basic ' + base64.b64encode(b'player:incorrect').decode()
        try:
            for _ in range(3):
                self.assertEqual(self.request('GET', '/', wrong)[0], 401)
            status, headers, data = self.request('GET', '/', wrong)
            self.assertEqual(status, 429)
            self.assertEqual(headers['Retry-After'], '90')
            self.assertEqual(self.request('GET', '/', self.good)[0], 429)
            clock.advance(91)
            self.assertEqual(self.request('GET', '/', self.good)[0], 200)
        finally:
            self.server.auth_limiter = old

    def test_stale_session_signals_reset(self):
        status, headers, data = self.request('GET', '/api/state', self.good)
        self.assertEqual(status, 200)
        cookie = headers.get('Set-Cookie').split(';', 1)[0]
        token = cookie.split('=', 1)[1]
        with self.server.sessions.lock:
            self.server.sessions.items.pop(token)
        req = Request(self.root + '/api/state', headers={
            'Authorization': self.good, 'Cookie': cookie,
        })
        with urlopen(req, timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['X-Tal-Session-Reset'], '1')
            self.assertNotEqual(response.headers.get('Set-Cookie').split(';')[0], cookie)


class LogicTests(unittest.TestCase):
    def test_limiter_window_and_recovery(self):
        clock = FakeClock()
        limit = AuthLimiter(max_failures=3, window=15, penalty=30, clock=clock)
        limit.failure('x'); limit.failure('x')
        clock.advance(16)
        self.assertEqual(limit.wait_seconds('x'), 0)
        limit.failure('x')  # old window entries no longer count
        self.assertEqual(limit.wait_seconds('x'), 0)
        limit.failure('x'); limit.failure('x')
        self.assertEqual(limit.wait_seconds('x'), 30)
        clock.advance(31)
        self.assertEqual(limit.wait_seconds('x'), 0)
        limit.failure('x'); limit.success('x')
        self.assertEqual(len(limit.clients), 0)

    def test_reclaims_only_idle_sessions(self):
        clock = FakeClock()
        sessions = Sessions(maximum=2, ttl=7200, idle_reclaim=1200, clock=clock)
        old_sid, old_game, _ = sessions.session(None)
        clock.advance(600)
        active_sid, active_game, _ = sessions.session(None)
        with self.assertRaises(Exception):
            sessions.session(None)
        clock.advance(610)
        # Refresh a still-active client's session; only the old one is reclaimable.
        self.assertIs(sessions.session(active_sid)[1], active_game)
        replacement_sid, _, _ = sessions.session(None)
        self.assertNotEqual(replacement_sid, old_sid)
        self.assertNotIn(old_sid, sessions.items)
        self.assertIn(active_sid, sessions.items)

    def test_search_queue_timeout_is_user_visible_and_recoverable(self):
        game = Game()
        gate = threading.Lock()
        self.assertTrue(gate.acquire())
        game.search_gate = gate
        game.search_wait_seconds = .05
        try:
            game.new({'side': 'black', 'depth': 1, 'seconds': .1})
            deadline = time.monotonic() + 2
            while game.state()['thinking'] and time.monotonic() < deadline:
                time.sleep(.01)
            state = game.state()
            self.assertFalse(state['thinking'])
            self.assertIn('다른 대국', state['error'])
            self.assertEqual(state['moves'], [])
        finally:
            gate.release()
        game.new({'side': 'black', 'depth': 1, 'seconds': .1})
        deadline = time.monotonic() + 5
        while game.state()['thinking'] and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertFalse(game.state()['thinking'])
        self.assertIsNone(game.state()['error'])
        self.assertEqual(len(game.state()['moves']), 1)


class EvaluationCacheTests(unittest.TestCase):
    def setUp(self):
        self.flags = (evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY)
        evaluate.clear_pawn_cache()

    def tearDown(self):
        evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE, evaluate.KING_SAFETY = self.flags
        evaluate.clear_pawn_cache()

    def test_cached_attack_map_is_reused_and_immutable(self):
        evaluate.ATTACK_ACTIVITY = True
        evaluate.INITIATIVE = True
        b = Board()
        score = evaluate.evaluate_white(b)
        entry = next(iter(evaluate._PAWN_CACHE.values()))
        attacks = entry[4]['_activity_guarded']
        self.assertTrue(all(isinstance(side, frozenset) for side in attacks))
        for _ in range(5):
            self.assertEqual(evaluate.evaluate_white(b), score)
            self.assertIs(entry[4]['_activity_guarded'], attacks)
        b.push_uci('e2e4')
        self.assertEqual(evaluate.evaluate_white(b), evaluate.evaluate_white_terms(b))
        self.assertEqual(len(evaluate._PAWN_CACHE), 2)

    def test_reference_eval_matches_with_all_attack_feature_combinations(self):
        import json
        from pathlib import Path
        examples = json.loads((Path(__file__).parent / 'tal_positions.json').read_text())['positions']
        positions = [Board()] + [Board(item['fen']) for item in examples]
        # Exercise the same pawn structures with different moved minor pieces.
        opening = Board()
        for m in 'e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1'.split():
            opening.push_uci(m)
            positions.append(Board(opening.fen()))
        for attack in (False, True):
            for initiative in (False, True):
                for safety in (False, True):
                    evaluate.ATTACK_ACTIVITY = attack
                    evaluate.INITIATIVE = initiative
                    evaluate.KING_SAFETY = safety
                    for b in positions:
                        self.assertEqual(evaluate.evaluate_white(b),
                                         evaluate.evaluate_white_terms(b),
                                         (attack, initiative, safety, b.fen()))


if __name__ == '__main__':
    unittest.main(verbosity=2)
