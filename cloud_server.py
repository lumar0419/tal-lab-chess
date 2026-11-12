"""Tal Lab v0.5.1: password-protected cloud deployment (Python stdlib only).

Use Render's RENDER_EXTERNAL_HOSTNAME and PORT automatically. Hosting requires a
strong TAL_SITE_PASSWORD configured in the hosting dashboard, never in Git.

All games are kept in process RAM and disappear on restart/spin-down.
"""

import argparse
import base64
import binascii
from collections import OrderedDict
import hmac
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

from web_server import Game, WebHandler

SESSION_COOKIE = 'tal_lab_sid'
SESSION_TTL = 2 * 60 * 60
MAX_SESSIONS = 16
GLOBAL_SEARCH_GATE = threading.Lock()


class CloudGame(Game):
    """Share the evaluation-feature lock across all browser sessions.

    evaluate.py uses global option flags, so independent Game() gates would
    otherwise produce corrupted cross-session evaluations during searches.
    """

    def __init__(self):
        super().__init__()
        self.search_gate = GLOBAL_SEARCH_GATE

    def pgn(self):
        return super().pgn().replace('Tal Lab Local Game', 'Tal Lab Cloud Game').replace(
            '[Site "localhost"]', '[Site "Tal Lab Cloud"]'
        )


class SessionLimitError(Exception):
    pass


class Sessions:
    """Bounded in-memory game sessions, identified by unpredictable cookies."""

    def __init__(self, ttl=SESSION_TTL, maximum=MAX_SESSIONS):
        self.ttl = ttl
        self.maximum = maximum
        self.lock = threading.Lock()
        self.items = OrderedDict()  # token => (CloudGame, last_seen_epoch)

    def session(self, token):
        now = time.monotonic()
        with self.lock:
            if token in self.items:
                game, last = self.items[token]
                if now - last < self.ttl:
                    self.items.move_to_end(token)
                    self.items[token] = (game, now)
                    return token, game, False
                del self.items[token]
            # Evict only inactive sessions; never silently reset a current game.
            for old_token, (game, last) in list(self.items.items()):
                if now - last >= self.ttl:
                    self.items.pop(old_token, None)
            if len(self.items) >= self.maximum:
                raise SessionLimitError('동시 접속 가능한 대국 수를 초과했어요. 잠시 후 다시 시도해 주세요.')
            new_token = secrets.token_urlsafe(32)
            game = CloudGame()
            self.items[new_token] = (game, now)
            return new_token, game, True


def cookie_token(raw):
    if len(raw) > 4096:
        return None
    try:
        cookies = SimpleCookie()
        cookies.load(raw)
        item = cookies.get(SESSION_COOKIE)
        token = item.value if item else None
        return token if token and len(token) <= 128 else None
    except Exception:
        return None


class CloudHandler(WebHandler):
    server_version = 'TalLabCloud/0.5.1'

    def _host_allowed(self):
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
        except ValueError:
            return False
        return host is not None and host.lower() == self.server.public_host.lower()

    def _origin_allowed(self):
        # Require an Origin header for state-changing browser requests.
        origin = self.headers.get('Origin', '')
        try:
            uri = urlsplit(origin)
            return (uri.hostname is not None and
                    uri.hostname.lower() == self.server.public_host.lower() and
                    uri.scheme == ('https' if self.server.secure else 'http') and
                    (uri.port is None if self.server.secure else uri.port in (None, self.server.server_port)))
        except ValueError:
            return False

    def _authorized(self):
        header = self.headers.get('Authorization', '')
        if not header.startswith('Basic ') or len(header) > 1024:
            return False
        try:
            plain = base64.b64decode(header[6:], validate=True).decode('utf-8')
            username, password = plain.split(':', 1)
        except (ValueError, UnicodeError, binascii.Error):
            return False
        return (hmac.compare_digest(username.encode("utf-8"), self.server.auth_user.encode("utf-8")) and
                hmac.compare_digest(password.encode("utf-8"), self.server.auth_password.encode("utf-8")))

    def _response(self, status, content, content_type='application/json; charset=utf-8', extra=None):
        extra = dict(extra or {})
        extra['Content-Security-Policy'] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'none'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'"
        )
        extra['Cross-Origin-Resource-Policy'] = 'same-origin'
        if getattr(self, '_new_sid', None):
            cookie = f'{SESSION_COOKIE}={self._new_sid}; Path=/; HttpOnly; SameSite=Strict'
            if self.server.secure:
                cookie += '; Secure'
            extra['Set-Cookie'] = cookie
        super()._response(status, content, content_type, extra)

    def _reject_auth(self):
        self._response(401, b'Authentication required', 'text/plain; charset=utf-8',
                       {'WWW-Authenticate': 'Basic realm="Tal Lab Chess", charset="UTF-8"'})

    def _prepare_game(self):
        try:
            sid, game, is_new = self.server.sessions.session(cookie_token(self.headers.get('Cookie', '')))
        except SessionLimitError as exc:
            self._json(503, {'error': str(exc)})
            return False
        self.game = game
        self._new_sid = sid if is_new else None
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            self._response(200, b'ok\n', 'text/plain; charset=utf-8')
            return
        if path == '/robots.txt':
            self._response(200, b'User-agent: *\nDisallow: /\n', 'text/plain; charset=utf-8')
            return
        if not self._host_allowed():
            self._json(403, {'error': '요청 호스트를 확인할 수 없어요.'})
            return
        if not self._authorized():
            self._reject_auth()
            return
        if self._prepare_game():
            super().do_GET()

    def do_POST(self):
        if not self._host_allowed() or not self._origin_allowed():
            self._json(403, {'error': '허용되지 않은 요청이에요.'})
            return
        if not self._authorized():
            self._reject_auth()
            return
        if self._prepare_game():
            super().do_POST()

    def log_message(self, format, *args):
        # Do not log credentials, browser cookies, or game data.
        if self.path not in ('/api/state', '/healthz'):
            super().log_message(format, *args)


def make_cloud_server(port, *, host='0.0.0.0', public_host, auth_user,
                      auth_password, secure=True):
    if not auth_password or len(auth_password) < 12:
        raise ValueError('TAL_SITE_PASSWORD에는 12자 이상의 전용 비밀번호를 지정하세요.')
    if not public_host:
        raise ValueError('RENDER_EXTERNAL_HOSTNAME 또는 TAL_PUBLIC_HOST가 필요해요.')
    server = ThreadingHTTPServer((host, port), CloudHandler)
    server.daemon_threads = True
    server.public_host = public_host
    server.auth_user = auth_user
    server.auth_password = auth_password
    server.secure = secure
    server.sessions = Sessions()
    return server


def main():
    parser = argparse.ArgumentParser(description='Tal Lab v0.5.1 cloud chess')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', '10000')))
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME') or os.environ.get('TAL_PUBLIC_HOST')
    username = os.environ.get('TAL_SITE_USER', 'player')
    password = os.environ.get('TAL_SITE_PASSWORD', '')
    secure = os.environ.get('TAL_INSECURE_LOCAL_TEST') != '1'
    try:
        server = make_cloud_server(args.port, host=args.host, public_host=hostname,
                                   auth_user=username, auth_password=password, secure=secure)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'Tal Lab cloud ready: host={hostname} port={server.server_port}', flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
