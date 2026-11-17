"""Tal Lab Web — standard-library localhost web interface for the v0.4.11 chess engine.

Run: python web_server.py
No external Python packages required. Localhost only by default.
"""

import argparse
import json
import mimetypes
import os
import re
import threading
import time
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from version import VERSION
import evaluate
from board import BLACK, EMPTY, START_FEN, WHITE, Board, file_of, rank_of, sq, sq_name
from search import Searcher, format_score

BASE = Path(__file__).resolve().parent
ASSETS = BASE / 'web'
OPTION_KEYS = ('tactical_checks', 'attack_activity', 'initiative',
               'tactical_ordering', 'check_continuation', 'aspiration', 'king_safety', 'lmr',
               'selective', 'tactical')
ENGINE_FILES = ('version.py', 'board.py', 'evaluate.py', 'search.py', 'notation.py', 'analysis_server.py', 'benchmark.py', 'pgn_io.py', 'sacrifice.py', 'search_gate.py', 'deep_analysis.py')
DEFAULT_OPTIONS = {key: False for key in OPTION_KEYS}
SELECTIVE_EXTRA_DEPTH = 3      # 선택적 탐색을 켠 대국에서 깊이 상한에 더하는 반수 (v0.8.8)
ALLOWED_ASSETS = {
    '/engine-worker.js': ('engine-worker.js', 'application/javascript; charset=utf-8'),
    '/analysis-visuals.js': ('analysis-visuals.js', 'application/javascript; charset=utf-8'),
    '/': ('analysis.html', 'text/html; charset=utf-8'),
    '/analysis': ('analysis.html', 'text/html; charset=utf-8'),
    '/play': ('index.html', 'text/html; charset=utf-8'),
    '/analysis.js': ('analysis.js', 'application/javascript; charset=utf-8'),
    '/analysis.css': ('analysis.css', 'text/css; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
    '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
}


from notation import san_for_move
from search_gate import GAME, MANUAL, SearchGate, acquire_search


class Game:
    """One local game. API moves are serialized, engine search runs on a worker.

    Important: evaluate.py uses module-global feature flags. The search gate ensures
    two old/new search jobs cannot evaluate with different flag values concurrently.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.search_gate = SearchGate()
        self.search_wait_seconds = None  # Local games may wait; hosted games use a deadline.
        self.worker_searcher = None
        self._cached_searcher = None  # TT is carried between moves of ONE game only.
        self.generation = 0
        self.board = Board()
        self.human = WHITE
        self.depth = 4
        self.seconds = 0.7
        self.options = dict(DEFAULT_OPTIONS)
        self.moves = []
        self.thinking = False
        self.info = None
        self.ending = None
        self.error = None
        self.start_date = date.today().strftime('%Y.%m.%d')
        self._analysis = None

    def analysis(self):
        # Construct lazily: CloudGame replaces search_gate after Game.__init__.
        with self.lock:
            if self._analysis is None:
                from analysis_server import AnalysisSession
                self._analysis = AnalysisSession(self.search_gate, self.search_wait_seconds,
                                                 san_for_move=san_for_move)
            return self._analysis

    def _stop_locked(self):
        self.generation += 1
        if self.worker_searcher is not None:
            self.worker_searcher.stop_requested = True
        self.thinking = False

    def _outcome_locked(self):
        return self.ending if self.ending is not None else self.board.outcome()

    def _start_engine_locked(self):
        if self._outcome_locked() is not None or self.board.side == self.human:
            return
        if self.thinking:
            return
        self.thinking = True
        self.info = None
        self.error = None
        generation = self.generation
        position = self.board.snapshot()
        params = (self.depth, self.seconds, dict(self.options), generation, position)
        threading.Thread(target=self._engine_worker, args=params, daemon=True).start()

    def _engine_worker(self, depth, seconds, options, generation, position):
        # The evaluator currently has global feature flags. Never run searches
        # with different feature settings concurrently in the same process.
        acquired = acquire_search(self.search_gate, GAME, threading.Event(),
                                  lambda: generation != self.generation, self.search_wait_seconds)
        if not acquired:
            with self.lock:
                if generation == self.generation:
                    self.thinking = False
                    self.error = ('엔진이 다른 대국을 계산 중이에요. '
                                  '잠시 후 새 대국을 시작하거나 다시 시도해 주세요.')
            return
        searcher = None
        keys = ('ATTACK_ACTIVITY', 'INITIATIVE', 'KING_SAFETY')
        saved_eval = {key: getattr(evaluate, key) for key in keys}
        try:
            with self.lock:
                if generation != self.generation:
                    return
                original_fen = self.board.fen()
                if self._cached_searcher is None:
                    self._cached_searcher = Searcher(tt_size=60_000)
                searcher = self._cached_searcher
                self.worker_searcher = searcher
            # Snapshot includes past history for correct repetition detection.
            search_board = Board(original_fen)
            search_board.restore(position)
            searcher.qsearch_quiet_checks = options['tactical_checks']
            searcher.tactical_ordering = options['tactical_ordering']
            searcher.check_continuation = options['check_continuation']
            searcher.aspiration = options['aspiration']
            searcher.lmr = options['lmr']
            searcher.selective = options['selective']
            searcher.set_tactical(options['tactical'])
            evaluate.ATTACK_ACTIVITY = options['attack_activity']
            evaluate.INITIATIVE = options['initiative']
            evaluate.KING_SAFETY = options['king_safety']
            last_info = None

            def on_info(info):
                nonlocal last_info
                last_info = info
                with self.lock:
                    if generation == self.generation:
                        self.info = {
                            'depth': info.depth,
                            'nodes': info.nodes,
                            'seconds': round(info.seconds, 3),
                            'score': info.score if search_board.side == WHITE else -info.score,
                            'pv': [m.uci() for m in info.pv],
                        }

            # 선택적 탐색은 같은 시간에 더 깊이 가지만 같은 깊이에서는 가지를 덜 본다.
            # 화면의 '깊이'를 그대로 상한으로 쓰면 오히려 얕게 끝나므로 상한을 넉넉히 준다.
            limit = depth + (SELECTIVE_EXTRA_DEPTH if options['selective'] or options['tactical'] else 0)
            move, score = searcher.search(search_board, max_depth=limit,
                                          time_limit=seconds, on_info=on_info,
                                          cancel_check=lambda: generation != self.generation)
            with self.lock:
                if generation != self.generation:
                    return
                if self._outcome_locked() is not None:
                    self.thinking = False
                    return
                if move is None:
                    raise RuntimeError('엔진이 둘 수 있는 수를 반환하지 않았어요.')
                # The worker must not mutate the live board unless the move is still legal.
                legal_move = self.board.parse_uci(move.uci())
                if legal_move is None:
                    raise RuntimeError('엔진이 현재 국면에서 불법수를 반환했어요.')
                san = san_for_move(self.board, legal_move)
                self.moves.append({'uci': legal_move.uci(), 'san': san, 'side': self.board.side})
                self.board.make_move(legal_move)
                self.thinking = False
                if last_info is None:
                    self.info = {'depth': 0, 'nodes': searcher.nodes,
                                 'seconds': round(time.monotonic() - searcher.start, 3),
                                 'score': score if search_board.side == WHITE else -score,
                                 'pv': [move.uci()]}
        except Exception as exc:
            with self.lock:
                if generation == self.generation:
                    self.thinking = False
                    self.error = '엔진 계산 오류: ' + str(exc)
        finally:
            with self.lock:
                if self.worker_searcher is searcher:
                    self.worker_searcher = None
            for key, value in saved_eval.items():
                setattr(evaluate, key, value)
            self.search_gate.release()

    def new(self, data):
        if not isinstance(data, dict):
            raise ValueError('설정 형식이 잘못됐어요.')
        human = {'white': WHITE, 'black': BLACK}.get(data.get('side', 'white'))
        if human is None:
            raise ValueError('선수 색상은 white 또는 black이어야 해요.')
        depth = data.get('depth', 4)
        seconds = data.get('seconds', 0.7)
        if type(depth) is not int or not 1 <= depth <= 7:
            raise ValueError('깊이는 1~7의 정수여야 해요.')
        if type(seconds) not in (int, float) or not 0.1 <= seconds <= 5.0:
            raise ValueError('생각 시간은 0.1~5초여야 해요.')
        options = data.get('options', {})
        if not isinstance(options, dict) or set(options) - set(OPTION_KEYS):
            raise ValueError('지원하지 않는 공격 설정이 포함됐어요.')
        if any(type(value) is not bool for value in options.values()):
            raise ValueError('공격 설정 값은 true/false여야 해요.')
        with self.lock:
            self._stop_locked()
            self._cached_searcher = None  # new game/options must not reuse old TT scores
            self.board = Board()
            self.moves = []
            self.human = human
            self.depth = depth
            self.seconds = float(seconds)
            self.options = {key: options.get(key, False) for key in OPTION_KEYS}
            self.info = None
            self.ending = None
            self.error = None
            self.start_date = date.today().strftime('%Y.%m.%d')
            self._start_engine_locked()
            return self.state_locked()

    def move(self, text):
        if not isinstance(text, str) or not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', text):
            raise ValueError('수는 e2e4 또는 e7e8q 형식이어야 해요.')
        with self.lock:
            if self._outcome_locked() is not None:
                raise ValueError('이미 종료된 대국이에요.')
            if self.thinking or self.board.side != self.human:
                raise ValueError('지금은 엔진의 차례예요.')
            move = self.board.parse_uci(text)
            if move is None:
                raise ValueError('현재 국면에서는 둘 수 없는 수예요.')
            san = san_for_move(self.board, move)
            self.moves.append({'uci': move.uci(), 'san': san, 'side': self.board.side})
            self.board.make_move(move)
            self.error = None
            self._start_engine_locked()
            return self.state_locked()

    def undo(self):
        with self.lock:
            if not any(record['side'] == self.human for record in self.moves):
                raise ValueError('되돌릴 수 있는 플레이어의 수가 없어요.')
            self._stop_locked()
            self.ending = None
            self.error = None
            self.info = None
            while self.moves:
                record = self.moves.pop()
                self.board.unmake_move()
                if record['side'] == self.human:
                    break
            return self.state_locked()

    def draw(self):
        with self.lock:
            if self.thinking or self.board.side != self.human or self._outcome_locked():
                raise ValueError('지금은 무승부를 청구할 수 없어요.')
            reason = self.board.claimable_draw()
            if reason is None:
                raise ValueError('현재는 3회 반복 또는 50수 규칙을 충족하지 않았어요.')
            self.ending = ('1/2-1/2', '플레이어 무승부 청구: ' + reason)
            return self.state_locked()

    def resign(self):
        with self.lock:
            if self._outcome_locked() is not None:
                raise ValueError('이미 종료된 대국이에요.')
            self._stop_locked()
            self.ending = ('0-1' if self.human == WHITE else '1-0', '플레이어 기권')
            return self.state_locked()

    def state_locked(self):
        b = self.board
        ended = self._outcome_locked()
        can_play = ended is None and not self.thinking and b.side == self.human
        last = self.moves[-1]['uci'] if self.moves else None
        return {
            'board': [[b.board[sq(f, r)] for f in range(8)] for r in range(7, -1, -1)],
            'fen': b.fen(),
            'side_to_move': 'white' if b.side == WHITE else 'black',
            'human': 'white' if self.human == WHITE else 'black',
            'depth': self.depth,
            'seconds': self.seconds,
            'options': dict(self.options),
            'moves': [{k: v for k, v in record.items() if k != 'side'} for record in self.moves],
            'legal': [move.uci() for move in b.legal_moves()] if can_play else [],
            'check': sq_name(b.king_sq[b.side]) if b.in_check() else None,
            'last_move': last,
            'thinking': self.thinking,
            'outcome': {'result': ended[0], 'reason': ended[1]} if ended else None,
            'claimable_draw': b.claimable_draw() if can_play else None,
            'can_undo': any(m['side'] == self.human for m in self.moves),
            'info': dict(self.info) if self.info else None,
            'error': self.error,
            'version': VERSION,
            'engine_version': VERSION,
        }

    def state(self):
        with self.lock:
            return self.state_locked()

    def pgn(self):
        with self.lock:
            result = self._outcome_locked()
            label = result[0] if result else '*'
            white = 'Player' if self.human == WHITE else 'Tal Lab v0.8.6'
            black = 'Player' if self.human == BLACK else 'Tal Lab v0.8.6'
            headers = [
                '[Event "Tal Lab Local Game"]',
                '[Site "localhost"]',
                '[Date "%s"]' % self.start_date,
                '[White "%s"]' % white,
                '[Black "%s"]' % black,
                '[Result "%s"]' % label,
            ]
            tokens = []
            for i, move in enumerate(self.moves):
                if i % 2 == 0:
                    tokens.append(str(i // 2 + 1) + '.')
                tokens.append(move['san'])
            tokens.append(label)
            return '\n'.join(headers) + '\n\n' + ' '.join(tokens) + '\n'


class WebHandler(BaseHTTPRequestHandler):
    game = None  # set on the subclass created by make_server
    server_version = 'TalLab/0.8.6'

    def _response(self, status, content, content_type='application/json; charset=utf-8', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(content)

    def _json(self, status, data):
        self._response(status, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _host_allowed(self):
        values = self.headers.get_all('Host', [])
        if len(values) != 1:
            return False
        host = values[0].lower()
        name, sep, port = host.rpartition(':')
        if sep and port.isascii() and port.isdecimal() and len(port) <= 5 and 1 <= int(port) <= 65535:
            host = name
        return host in ('127.0.0.1', 'localhost', '[::1]')

    def _origin_allowed(self):
        origin = self.headers.get('Origin')
        if not origin:
            return True
        try:
            url = urlsplit(origin)
            return url.hostname in ('127.0.0.1', 'localhost', '::1') and url.port == self.server.server_port
        except ValueError:
            return False

    def do_GET(self):
        if not self._host_allowed():
            self._json(403, {'error': '허용되지 않은 호스트예요.'})
            return
        path = urlsplit(self.path).path
        if path == '/api/analysis/state':
            self._json(200, self.game.analysis().state())
            return
        if path == '/api/analysis/cases':
            try:
                data = json.loads((BASE / 'master_sacrifice_cases.json').read_text(encoding='utf-8'))
                self._json(200, {'positions': data.get('positions', [])})
            except (OSError, ValueError):
                self._json(500, {'error': '마스터 국면 데이터를 불러올 수 없어요.'})
            return
        if path == '/api/state':
            self._json(200, self.game.state())
            return
        if path == '/api/pgn':
            data = self.game.pgn().encode('utf-8')
            self._response(200, data, 'application/x-chess-pgn; charset=utf-8',
                           {'Content-Disposition': 'attachment; filename="tal-lab-game.pgn"'})
            return
        if path.startswith('/engine/') and path[8:] in ENGINE_FILES:
            self._response(200, (BASE / path[8:]).read_bytes(), 'text/plain; charset=utf-8')
            return
        asset = ALLOWED_ASSETS.get(path)
        if not asset:
            self._json(404, {'error': '찾을 수 없는 페이지예요.'})
            return
        try:
            data = (ASSETS / asset[0]).read_bytes()
        except OSError:
            self._json(500, {'error': '웹 파일을 읽을 수 없어요.'})
            return
        self._response(200, data, asset[1])

    def do_POST(self):
        if not self._host_allowed() or not self._origin_allowed():
            self._json(403, {'error': '허용되지 않은 요청이에요.'})
            return
        path = urlsplit(self.path).path
        routes = {'/api/new', '/api/move', '/api/undo', '/api/resign', '/api/draw',
                  '/api/analysis/pgn', '/api/analysis/navigate', '/api/analysis/sacrifice', '/api/analysis/benchmark', '/api/analysis/start', '/api/analysis/auto', '/api/analysis/restart',
                  '/api/analysis/stop', '/api/analysis/evaluation', '/api/analysis/fen',
                  '/api/analysis/move', '/api/analysis/undo', '/api/analysis/reset'}
        if path not in routes:
            self._json(404, {'error': '지원하지 않는 기능이에요.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if size < 0 or size > (140000 if path == '/api/analysis/pgn' else 8192):
                self._json(413, {'error': '요청 크기가 허용 범위를 벗어났어요.'})
                return
            obj = json.loads(self.rfile.read(size))
            if not isinstance(obj, dict):
                raise ValueError('JSON 객체가 필요해요.')
            if path == '/api/analysis/evaluation':
                state = self.game.analysis().evaluation(obj)
            elif path == '/api/analysis/pgn':
                state = self.game.analysis().import_pgn(obj.get('pgn'))
            elif path == '/api/analysis/navigate':
                state = self.game.analysis().navigate(obj.get('ply'))
            elif path == '/api/analysis/sacrifice':
                state = self.game.analysis().sacrifice(obj)
            elif path == '/api/analysis/benchmark':
                gate = self.game.search_gate
                if not acquire_search(gate, MANUAL, threading.Event(), lambda: False, 0.5):
                    self._json(409, {'error': '분석을 중단한 뒤 벤치마크를 실행하세요.'})
                    return
                try:
                    from benchmark import run_benchmark
                    state = run_benchmark()
                finally:
                    gate.release()
            elif path == '/api/analysis/start':
                state = self.game.analysis().start(obj)
            elif path == '/api/analysis/auto':
                state = self.game.analysis().start(obj, mode='auto')
            elif path == '/api/analysis/restart':
                state = self.game.analysis().start(obj, mode='restart')
            elif path == '/api/analysis/stop':
                state = self.game.analysis().stop()
            elif path == '/api/analysis/fen':
                state = self.game.analysis().set_fen(obj.get('fen'))
            elif path == '/api/analysis/move':
                state = self.game.analysis().move(obj.get('uci'))
            elif path == '/api/analysis/undo':
                state = self.game.analysis().undo()
            elif path == '/api/analysis/reset':
                state = self.game.analysis().reset()
            elif path == '/api/new':
                state = self.game.new(obj)
            elif path == '/api/move':
                state = self.game.move(obj.get('uci'))
            elif path == '/api/undo':
                state = self.game.undo()
            elif path == '/api/resign':
                state = self.game.resign()
            else:
                state = self.game.draw()
            self._json(200, state)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {'error': str(exc)})
        except Exception as exc:
            self._json(500, {'error': '서버 처리 중 오류가 발생했어요.'})

    def log_message(self, format, *args):
        # Keep console concise and avoid printing every status poll.
        if self.path != '/api/state':
            super().log_message(format, *args)


def make_server(port=8000, game=None):
    game = game or Game()
    handler = type('TalLabHandler', (WebHandler,), {'game': game})
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description='Tal Lab v0.8.6 auto analysis website')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = make_server(args.port)
    except OSError as exc:
        print('서버를 시작하지 못했어요:', exc)
        print('다른 포트를 시도하세요: python web_server.py --port 8001')
        raise SystemExit(1)
    url = f'http://127.0.0.1:{server.server_port}'
    print('\n  ♟  Tal Lab v0.8.6 — Auto Analysis Studio')
    print('  주소:', url)
    print('  서버 종료: Ctrl+C')
    print('  이 웹사이트는 내 컴퓨터에서만 접속할 수 있어요.\n')
    if not args.no_browser:
        threading.Timer(0.65, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print('\n서버를 종료합니다.')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
