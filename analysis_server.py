"""Position analysis for Tal Lab v0.5.4.

No autoplay: both sides' legal moves are available. Iterative search results are
published after *completed* depths. A minimum target does NOT override the hard
time cap, so an expensive position may finish below the selected target.
"""

from __future__ import annotations

import re
import threading
import time

import evaluate
from board import Board, WHITE, START_FEN, file_of, rank_of, sq, sq_name
from search import Searcher, TimeUp

ANALYSIS_OPTION_KEYS = ('tactical_checks', 'attack_activity', 'initiative',
                        'tactical_ordering', 'check_continuation', 'aspiration',
                        'king_safety', 'lmr')


class AnalysisSession:
    def __init__(self, search_gate, search_wait_seconds=None, san_for_move=None):
        self.lock = threading.RLock()
        self.search_gate = search_gate
        self.search_wait_seconds = search_wait_seconds
        self.san_for_move = san_for_move
        self.board = Board()
        self.base_fen = START_FEN
        self.moves = []
        self.epoch = 0
        self.searcher = None
        self.active = False
        self.status = 'idle'
        self.error = None
        self.completed = None
        self.iterations = []
        self.attempting = 0
        self.min_depth = 5
        self.max_depth = 8
        self.seconds = 30
        self.options = {key: False for key in ANALYSIS_OPTION_KEYS}
        self.started_at = None
        self.elapsed = 0.0

    def _stop_locked(self):
        self.epoch += 1
        if self.searcher is not None:
            self.searcher.stop_requested = True
        self.searcher = None
        self.active = False

    def _clear_analysis_locked(self):
        self._stop_locked()
        self.status = 'idle'
        self.error = None
        self.completed = None
        self.iterations = []
        self.attempting = 0
        self.elapsed = 0.0
        self.started_at = None

    def set_fen(self, fen):
        if not isinstance(fen, str) or len(fen) > 180:
            raise ValueError('유효한 FEN 문자열을 입력해 주세요.')
        fresh = Board(fen)
        with self.lock:
            self._clear_analysis_locked()
            self.board = fresh
            self.base_fen = fresh.fen()
            self.moves = []
            return self._state_locked()

    def reset(self):
        return self.set_fen(START_FEN)

    def move(self, uci):
        if not isinstance(uci, str) or not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', uci):
            raise ValueError('이동은 e2e4 또는 e7e8q 형태로 입력해 주세요.')
        with self.lock:
            m = self.board.parse_uci(uci)
            if m is None:
                raise ValueError('현재 국면에서 합법적인 수가 아니에요.')
            san = self.san_for_move(self.board, m) if self.san_for_move else uci
            self._clear_analysis_locked()
            self.moves.append({'uci': m.uci(), 'san': san})
            self.board.make_move(m)
            return self._state_locked()

    def undo(self):
        with self.lock:
            if not self.moves:
                raise ValueError('되돌릴 수 있는 수가 없어요.')
            self._clear_analysis_locked()
            self.board.unmake_move()
            self.moves.pop()
            return self._state_locked()

    def stop(self):
        with self.lock:
            if self.active:
                self._stop_locked()
                self.status = 'stopped'
            return self._state_locked()

    def start(self, data):
        if not isinstance(data, dict):
            raise ValueError('분석 설정은 JSON 객체여야 해요.')
        minimum = data.get('min_depth', 5)
        maximum = data.get('max_depth', 8)
        seconds = data.get('seconds', 30)
        options = data.get('options', {})
        if (type(minimum) is not int or type(maximum) is not int or
                not 1 <= minimum <= maximum <= 10):
            raise ValueError('최소 목표 깊이 ≤ 최대 깊이 ≤ 10을 만족해야 해요.')
        if type(seconds) not in (float, int) or not 1 <= seconds <= 60:
            raise ValueError('최대 분석 시간은 1~60초여야 해요.')
        if (not isinstance(options, dict) or set(options) - set(ANALYSIS_OPTION_KEYS) or
                any(type(v) is not bool for v in options.values())):
            raise ValueError('지원하지 않는 분석 옵션이에요.')
        with self.lock:
            if self.active:
                raise ValueError('이미 분석 중이에요. 중단한 후 다시 시작해 주세요.')
            if self.board.outcome() is not None:
                raise ValueError('이미 종료된 국면이에요. 새로운 국면을 불러와 주세요.')
            self._clear_analysis_locked()
            self.min_depth = minimum
            self.max_depth = maximum
            self.seconds = float(seconds)
            self.options = {key: options.get(key, False) for key in ANALYSIS_OPTION_KEYS}
            self.active = True
            self.status = 'running'
            self.started_at = time.monotonic()
            epoch = self.epoch
            snapshot = self.board.snapshot()
            fen = self.board.fen()
            params = minimum, maximum, float(seconds), dict(self.options), epoch, fen, snapshot
            threading.Thread(target=self._worker, args=params, daemon=True).start()
            return self._state_locked()

    def _worker(self, minimum, maximum, seconds, options, epoch, fen, snapshot):
        if self.search_wait_seconds is None:
            acquired = self.search_gate.acquire()
        else:
            acquired = self.search_gate.acquire(timeout=self.search_wait_seconds)
        if not acquired:
            with self.lock:
                if epoch == self.epoch:
                    self.active = False
                    self.status = 'busy'
                    self.error = '다른 분석이 실행 중이에요. 잠시 후 다시 시도해 주세요.'
            return
        try:
            with self.lock:
                if epoch != self.epoch:
                    return
                worker = Searcher(tt_size=60_000)
                self.searcher = worker
            worker.qsearch_quiet_checks = options['tactical_checks']
            worker.tactical_ordering = options['tactical_ordering']
            worker.check_continuation = options['check_continuation']
            worker.aspiration = options['aspiration']
            worker.lmr = options['lmr']
            evaluate.ATTACK_ACTIVITY = options['attack_activity']
            evaluate.INITIATIVE = options['initiative']
            evaluate.KING_SAFETY = options['king_safety']
            b = Board(fen)
            b.restore(snapshot)
            turn_white = b.side == WHITE

            def on_iteration(depth):
                with self.lock:
                    if epoch != self.epoch:
                        # Also prevents a cancellation race: Searcher.search resets
                        # stop_requested at its start, so an old run must check its
                        # session epoch before starting the first iteration.
                        raise TimeUp()
                    self.attempting = depth

            def on_info(info):
                # Convert the latest completed PV to human-readable SAN, but
                # retain UCI moves for reproducible position navigation.
                pv_san = []
                if self.san_for_move:
                    view = Board(fen)
                    view.restore(snapshot)
                    for candidate in info.pv:
                        legal = view.parse_uci(candidate.uci())
                        if legal is None:
                            break
                        pv_san.append(self.san_for_move(view, legal))
                        view.make_move(legal)
                payload = {
                    'depth': info.depth,
                    'nodes': info.nodes,
                    'seconds': round(info.seconds, 3),
                    'score': info.score if turn_white else -info.score,
                    'pv': [m.uci() for m in info.pv],
                    'pv_san': pv_san,
                    'best_san': pv_san[0] if pv_san else None,
                }
                with self.lock:
                    if epoch != self.epoch:
                        return
                    self.completed = payload
                    self.iterations.append(payload)
                    self.elapsed = info.seconds

            worker.search(b, max_depth=maximum, min_depth=minimum,
                          time_limit=seconds, on_info=on_info, on_iteration=on_iteration,
                          full_time=True)
            with self.lock:
                if epoch != self.epoch:
                    return
                self.active = False
                self.status = ('target_not_reached' if
                               (self.completed is None or self.completed['depth'] < minimum)
                               else 'completed')
                self.elapsed = time.monotonic() - self.started_at
                self.searcher = None
        except Exception as exc:
            with self.lock:
                if epoch == self.epoch:
                    self.active = False
                    self.status = 'error'
                    self.error = '분석 오류: ' + str(exc)
                    self.searcher = None
        finally:
            self.search_gate.release()

    def _state_locked(self):
        b = self.board
        return {
            'board': [[b.board[sq(f, r)] for f in range(8)] for r in range(7, -1, -1)],
            'fen': b.fen(),
            'base_fen': self.base_fen,
            'side_to_move': 'white' if b.side == WHITE else 'black',
            'moves': list(self.moves),
            'legal': [m.uci() for m in b.legal_moves()],
            'check': sq_name(b.king_sq[b.side]) if b.in_check() else None,
            'outcome': b.outcome(),
            'active': self.active,
            'status': self.status,
            'error': self.error,
            'min_depth': self.min_depth,
            'max_depth': self.max_depth,
            'seconds': self.seconds,
            'options': dict(self.options),
            'attempting': self.attempting,
            'completed': dict(self.completed) if self.completed else None,
            'iterations': list(self.iterations),
            'elapsed': round(time.monotonic() - self.started_at, 2) if self.active and self.started_at else round(self.elapsed, 2),
            'version': '0.5.4',
        }

    def state(self):
        with self.lock:
            return self._state_locked()
