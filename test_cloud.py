"""Tests for hosted Tal Lab access and independent browser sessions (stdlib only)."""
import base64
import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from board import Board
from cloud_server import (
    CloudGame, GLOBAL_SEARCH_GATE, SESSION_COOKIE, Sessions,
    make_cloud_server,
)


class HostedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_cloud_server(
            0, host='127.0.0.1', public_host='127.0.0.1',
            auth_user='player', auth_password='secure-development-password', secure=False,
        )
        cls.root = 'http://127.0.0.1:%s' % cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.auth = 'Basic ' + base64.b64encode(b'player:secure-development-password').decode()
        cls.origin = cls.root

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def req(self, path, *, method='GET', data=None, cookie=None, auth=True, origin=None,
            host=None):
        headers = {}
        if auth:
            headers['Authorization'] = self.auth
        if cookie:
            headers['Cookie'] = cookie
        if origin:
            headers['Origin'] = origin
        if host:
            headers['Host'] = host
        if data is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(data).encode()
        request = Request(self.root + path, method=method, data=data, headers=headers)
        try:
            with urlopen(request, timeout=10) as resp:
                raw = resp.read()
                body = json.loads(raw) if resp.headers.get_content_type() == 'application/json' else raw
                return resp.status, resp.headers, body
        except HTTPError as err:
            raw = err.read()
            body = json.loads(raw) if err.headers.get_content_type() == 'application/json' else raw
            return err.code, err.headers, body

    def test_healthz_public(self):
        status, headers, body = self.req('/healthz', auth=False)
        self.assertEqual((status, body), (200, b'ok\n'))
        self.assertIsNone(headers.get('Set-Cookie'))

    def test_auth_required_and_host_restricted(self):
        status, headers, _ = self.req('/', auth=False)
        self.assertEqual(status, 401)
        self.assertIn('Basic', headers['WWW-Authenticate'])
        status, _, _ = self.req('/', host='evil.test')
        self.assertEqual(status, 403)

    def test_cookie_security_and_per_browser_games(self):
        status, headers, data = self.req('/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(data['fen'], Board().fen())
        raw_cookie = headers.get('Set-Cookie')
        self.assertIn('HttpOnly', raw_cookie)
        self.assertIn('SameSite=Strict', raw_cookie)
        a = raw_cookie.split(';',1)[0]
        self.assertTrue(a.startswith(SESSION_COOKIE+'='))
        status, headers_b, _ = self.req('/api/state')
        self.assertEqual(status, 200)
        b = headers_b.get('Set-Cookie').split(';',1)[0]
        self.assertNotEqual(a, b)
        status, _, state = self.req('/api/move', method='POST', data={'uci':'e2e4'},
                                    origin=self.origin, cookie=a)
        self.assertEqual(status, 200)
        self.assertEqual(state['moves'][0]['san'], 'e4')
        status, _, state2 = self.req('/api/state', cookie=b)
        self.assertEqual(status, 200)
        self.assertEqual(state2['moves'], [])
        self.assertEqual(state2['fen'], Board().fen())
        # Every CloudGame shares a global evaluation feature lock.
        self.assertIs(self.server.sessions.session(a.split('=',1)[1])[1].search_gate,
                      GLOBAL_SEARCH_GATE)

    def test_csrf_origin_and_password(self):
        status, headers, _ = self.req('/api/state')
        cookie = headers.get('Set-Cookie').split(';',1)[0]
        for origin in ('https://evil.test', None):
            status, _, _ = self.req('/api/new', method='POST', data={}, cookie=cookie,
                                    origin=origin)
            self.assertEqual(status, 403)
        status, _, _ = self.req('/api/new', method='POST', data={}, cookie=cookie,
                                origin=self.origin, auth=False)
        self.assertEqual(status, 401)
        status, _, state = self.req('/api/new', method='POST', data={'depth':2},
                                    cookie=cookie, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(state['depth'], 2)

    def test_website_assets_and_pgn(self):
        status, _, html = self.req('/')
        self.assertEqual(status, 200)
        self.assertIn(b'ANALYSIS STUDIO', html)
        status, _, play_html = self.req('/play')
        self.assertEqual(status, 200)
        self.assertIn(b'WEB EDITION', play_html)
        status, _, js = self.req('/app.js')
        self.assertEqual(status, 200)
        self.assertIn(b'onSquare', js)
        status, _, pgn = self.req('/api/pgn')
        self.assertEqual(status, 200)
        self.assertIn(b'Tal Lab Cloud Game', pgn)


class SessionTests(unittest.TestCase):
    def test_limit_and_reuse(self):
        s = Sessions(maximum=2)
        key1, g1, is_new = s.session(None)
        self.assertTrue(is_new)
        self.assertEqual(s.session(key1), (key1, g1, False))
        s.session(None)
        from cloud_server import SessionLimitError
        with self.assertRaises(SessionLimitError):
            s.session(None)

    def test_cloud_cookie_secure_and_unicode_auth(self):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        srv = make_cloud_server(0, host='127.0.0.1', public_host='127.0.0.1',
                                auth_user='player', auth_password='매우-강력한-패스워드-2026!', secure=True)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            auth = base64.b64encode('player:매우-강력한-패스워드-2026!'.encode()).decode()
            headers = {'Authorization': 'Basic ' + auth}
            with urlopen(Request('http://127.0.0.1:%s/' % srv.server_port, headers=headers),
                         timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn('Secure', resp.headers.get('Set-Cookie'))
            try:
                urlopen(Request('http://127.0.0.1:%s/' % srv.server_port,
                                headers={'Authorization': 'Basic INVALID!'}), timeout=5)
            except HTTPError as e:
                self.assertEqual(e.code, 401)
            else:
                self.fail('Invalid auth must be rejected')
        finally:
            srv.shutdown(); srv.server_close(); thread.join(timeout=2)

    def test_reject_short_password(self):
        with self.assertRaises(ValueError):
            make_cloud_server(0, public_host='localhost', auth_user='x', auth_password='weak')


if __name__ == '__main__':
    unittest.main(verbosity=2)
