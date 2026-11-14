"""Position analysis for Tal Lab v0.8.6.

No autoplay: both sides' legal moves are available. Iterative search results are
published after *completed* depths. A minimum target does NOT override the hard
time cap, so an expensive position may finish below the selected target.
"""

from __future__ import annotations

from copy import deepcopy
import re
import threading
import time

from version import VERSION
import evaluate
from board import Board, WHITE, START_FEN, file_of, rank_of, sq, sq_name
from search import Searcher, TimeUp
from search_gate import AUTO, DEEP, MANUAL, acquire_search
from deep_analysis import DEEP_SECONDS, analyze_deep

ANALYSIS_OPTION_KEYS = ('tactical_checks', 'attack_activity', 'initiative',
                        'tactical_ordering', 'check_continuation', 'aspiration',
                        'king_safety', 'lmr', 'selective')


class AnalysisSession:
    def __init__(self, search_gate, search_wait_seconds=None, san_for_move=None, *, background=True, on_update=None):
        self.background = background
        self.on_update = on_update
        self.lock = threading.RLock()
        self.search_gate = search_gate
        self.search_wait_seconds = search_wait_seconds
        self.san_for_move = san_for_move
        self.board = Board()
        self.base_fen = START_FEN
        self.moves = []
        self.game_moves = []
        self.game_scores = {}
        self.tags = {}
        self.epoch = 0
        self.searcher = None
        self.active = False
        self.mode = 'manual'
        self.deep = None
        self.status = 'idle'
        self.error = None
        self.completed = None
        self.iterations = []
        self.attempting = 0
        self.min_depth = 5
        self.max_depth = 8
        self.seconds = 30
        self.multipv = 3
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
        self.deep = None
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
            self.game_moves = []
            self.game_scores = {}
            self.tags = {}
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
            self.game_moves = list(self.moves)
            self.game_scores = {i:v for i,v in self.game_scores.items() if i < len(self.moves)}
            return self._state_locked()

    def undo(self):
        with self.lock:
            if not self.moves:
                raise ValueError('되돌릴 수 있는 수가 없어요.')
            return self.navigate(len(self.moves)-1)

    def import_pgn(self, text):
        from pgn_io import parse_pgn
        parsed = parse_pgn(text)  # atomic: invalid input leaves session untouched
        with self.lock:
            self.set_fen(parsed['base_fen'])
            self.game_moves = parsed['moves']
            self.tags = parsed['tags']
            return self._state_locked()

    def navigate(self, ply):
        with self.lock:
            if type(ply) is not int or not 0 <= ply <= len(self.game_moves):
                raise ValueError('기보 범위 안의 반수를 선택하세요.')
            self._clear_analysis_locked()
            self.board = Board(self.base_fen)
            self.moves = list(self.game_moves[:ply])
            for item in self.moves:
                self.board.make_move(self.board.parse_uci(item['uci']))
            return self._state_locked()

    def sacrifice(self, data):
        from sacrifice import analyze_candidate, discover_sacrifices
        discover = data.get('discover', False)
        if type(discover) is not bool:
            raise ValueError('희생 탐색 방식이 올바르지 않습니다.')
        with self.lock:
            if self.active: raise ValueError('현재 분석을 중단한 뒤 후보를 검증하세요.')
            if data.get('expected_fen') != self.board.fen(): raise ValueError('국면이 변경되었습니다.')
            b=Board(self.board.fen()); b.restore(self.board.snapshot())
            epoch = self.epoch
        def cancelled():
            return epoch != self.epoch

        if not acquire_search(self.search_gate, MANUAL, threading.Event(), cancelled,
                              min(0.5, self.search_wait_seconds or 0.5)):
            raise ValueError('다른 분석이 실행 중입니다.')
        try:
            # Fixed conservative limits protect the server. Main analysis can be
            # used for a longer follow-up with the same forced move's position.
            old = {k:getattr(evaluate,k) for k in ('ATTACK_ACTIVITY','INITIATIVE','KING_SAFETY')}
            try:
                for k in old: setattr(evaluate,k,False)
                if discover:
                    result = discover_sacrifices(b, depth=6, seconds=5, cancel_check=cancelled)
                else:
                    result = analyze_candidate(b, data.get('uci'), depth=5, seconds=5,
                                               cancel_check=cancelled)
                if cancelled():
                    raise ValueError('국면이 변경되었습니다.')
                result['fen']=b.fen()
                return result
            finally:
                for k,v in old.items(): setattr(evaluate,k,v)
        finally:
            self.search_gate.release()

    def stop(self):
        with self.lock:
            if self.active:
                if self.started_at is not None:
                    self.elapsed = time.monotonic() - self.started_at
                self.status = 'stopped'
                if self.deep:
                    self.deep = {**self.deep, 'outcome': 'cancelled', 'elapsed': round(self.elapsed, 3)}
            self._stop_locked()
            return self._state_locked()

    def start(self, data, *, mode='manual'):
        """Begin a bounded analysis.

        auto: only starts an idle position, never restarts an active/completed
              analysis (safe on page reload / multiple open tabs).
        restart: replaces a current search after an explicit setting change.
        Both require expected_fen so a delayed browser request cannot analyze
        an obsolete position and overwrite a more recent action.
        """
        if mode not in ('manual', 'auto', 'restart'):
            raise ValueError('지원하지 않는 분석 실행 방식이에요.')
        if not isinstance(data, dict):
            raise ValueError('분석 설정은 JSON 객체여야 해요.')
        if 'deep' in data and type(data['deep']) is not bool:
            raise ValueError('심층 분석 설정은 참 또는 거짓이어야 해요.')
        if data.get('deep') is True:
            if mode != 'manual':
                raise ValueError('심층 분석은 직접 시작해야 해요.')
            return self._start_deep(data)
        minimum = data.get('min_depth', 5)
        maximum = data.get('max_depth', 8)
        seconds = data.get('seconds', 30)
        multipv = data.get('multipv', 3)
        options = data.get('options', {})
        if (type(minimum) is not int or type(maximum) is not int or
                not 1 <= minimum <= maximum <= 10):
            raise ValueError('최소 목표 깊이 ≤ 최대 깊이 ≤ 10을 만족해야 해요.')
        if type(multipv) is not int or not 1 <= multipv <= 5:
            raise ValueError('후보 수(MultiPV)는 1~5개로 설정하세요.')
        if type(seconds) not in (float, int) or not 1 <= seconds <= 60:
            raise ValueError('최대 분석 시간은 1~60초여야 해요.')
        if (not isinstance(options, dict) or set(options) - set(ANALYSIS_OPTION_KEYS) or
                any(type(v) is not bool for v in options.values())):
            raise ValueError('지원하지 않는 분석 옵션이에요.')
        with self.lock:
            expected_epoch = data.get('expected_epoch')
            if expected_epoch is not None and expected_epoch != self.epoch:
                return self._state_locked()
            if mode != 'manual':
                expected_fen = data.get('expected_fen')
                if not isinstance(expected_fen, str) or len(expected_fen) > 180:
                    raise ValueError('자동 분석에는 현재 국면 FEN이 필요해요.')
                if expected_fen != self.board.fen():
                    return self._state_locked()  # stale request: no side effects
                if self.active and self.mode == 'deep':
                    return self._state_locked()
                if mode == 'auto' and self.status != 'idle':
                    return self._state_locked()  # no duplicate / restart loop
            if self.active and mode == 'manual' and self.mode != 'auto':
                raise ValueError('이미 분석 중이에요. 중단한 후 다시 시작해 주세요.')
            if self.board.outcome() is not None:
                if mode != 'manual':
                    return self._state_locked()  # checkmate/stalemate needs no search
                raise ValueError('이미 종료된 국면이에요. 새로운 국면을 불러와 주세요.')
            # Settings changes inherit the current job's priority. The UI's
            # automatic restart explicitly asks for auto priority.
            automatic = mode == 'auto' or (mode == 'restart' and
                (self.mode == 'auto' if self.active else data.get('automatic') is True))
            self._clear_analysis_locked()
            next_options = {key: options.get(key, False) for key in ANALYSIS_OPTION_KEYS}
            previous = self.game_scores.get(len(self.moves))
            if previous and previous['options'] != next_options:
                self.game_scores.pop(len(self.moves))
            self.mode = 'auto' if automatic else 'manual'
            self.min_depth = minimum
            self.max_depth = maximum
            self.seconds = float(seconds)
            self.multipv = multipv
            self.options = next_options
            self.active = True
            self.status = 'running'
            self.started_at = time.monotonic()
            epoch = self.epoch
            snapshot = self.board.snapshot()
            fen = self.board.fen()
            params = minimum, maximum, float(seconds), multipv, dict(self.options), epoch, fen, snapshot, automatic
            if self.background:
                threading.Thread(target=self._worker, args=params, daemon=True).start()
            else:
                self._worker(*params)
            return self._state_locked()

    def _start_deep(self, data):
        seconds = data.get('seconds')
        profile = data.get('profile', 'conservative')
        candidate = data.get('candidate')
        if type(seconds) is not int or seconds not in DEEP_SECONDS:
            raise ValueError('심층 분석 시간은 60·180·300·600초 중 하나를 선택하세요.')
        if profile not in ('conservative', 'full', 'selective'):
            raise ValueError('알 수 없는 심층 분석 설정이에요.')
        if candidate is not None and (not isinstance(candidate, str) or len(candidate) > 5):
            raise ValueError('후보 수는 d1d4 또는 e7e8q 형태로 입력해 주세요.')
        with self.lock:
            if data.get('expected_epoch', self.epoch) != self.epoch:
                return self._state_locked()
            if data.get('expected_fen', self.board.fen()) != self.board.fen():
                return self._state_locked()
            if self.active and self.mode != 'auto':
                raise ValueError('현재 분석을 중단한 뒤 다시 시작하세요.')
            if self.board.outcome():
                raise ValueError('이미 종료된 국면이에요.')
            if candidate and self.board.parse_uci(candidate) is None:
                raise ValueError('지정한 후보 수가 합법수가 아니에요.')
            self._clear_analysis_locked()
            self.game_scores.pop(len(self.moves), None)
            self.mode = 'deep'
            self.deep = {'profile': profile, 'phase': 'queued', 'budget': seconds, 'candidates': []}
            self.active = True
            self.status = 'running'
            self.started_at = time.monotonic()
            board = Board(self.board.fen())
            board.restore(self.board.snapshot())
            params = board, self.epoch, seconds, profile, candidate
            if self.background:
                threading.Thread(target=self._deep_worker, args=params, daemon=True).start()
            else:
                self._deep_worker(*params)
            return self._state_locked()

    def _deep_worker(self, board, epoch, seconds, profile, candidate):
        interrupted = threading.Event()

        def cancelled():
            return interrupted.is_set() or epoch != self.epoch

        def update(report):
            # Worker owns its report. Copy the nested lists before other threads
            # can serialize them. Do not publish stale jobs after a new move.
            with self.lock:
                if epoch != self.epoch:
                    return
                self.deep = deepcopy(report)
                if report['phase'] == 'root':
                    self.attempting = report['attempting']
            if self.on_update:
                self.on_update(self.state())

        white_to_move = board.side == WHITE
        snapshot = board.snapshot()

        def root_completed(info):
            pv_san = []
            if self.san_for_move:
                view = Board(board.fen())
                view.restore(snapshot)
                for move in info.pv:
                    pv_san.append(self.san_for_move(view, move))
                    view.make_move(move)
            line = {'rank': 1, 'sacrifice': None, 'depth': info.depth, 'nodes': info.nodes,
                    'seconds': round(info.seconds, 3),
                    'score': info.score if white_to_move else -info.score,
                    'pv': [move.uci() for move in info.pv], 'pv_san': pv_san,
                    'best_san': pv_san[0] if pv_san else None}
            with self.lock:
                if epoch != self.epoch:
                    return
                self.completed = {**line, 'candidates': [line]}
                self.iterations.append(self.completed)
                self.game_scores[len(self.moves)] = {
                    'ply': len(self.moves), 'score': line['score'], 'depth': line['depth'],
                    'multipv': 1, 'options': {'deep_profile': profile}}

        if not acquire_search(self.search_gate, DEEP, interrupted, cancelled, self.search_wait_seconds):
            with self.lock:
                if epoch == self.epoch:
                    self.active = False
                    self.status = 'busy'
                    self.error = '다른 분석이 실행 중이에요. 잠시 후 다시 시도해 주세요.'
            return
        eval_keys = ('ATTACK_ACTIVITY', 'INITIATIVE', 'KING_SAFETY')
        saved_eval = {key: getattr(evaluate, key) for key in eval_keys}
        try:
            for key in saved_eval:
                setattr(evaluate, key, False)
            analyze_deep(board, seconds, profile=profile, candidate=candidate,
                         cancel_check=cancelled, on_root=root_completed, on_progress=update)
            with self.lock:
                if epoch == self.epoch:
                    self.active = False
                    self.elapsed = time.monotonic() - self.started_at
                    self.status = ('preempted' if interrupted.is_set() else
                                   'completed' if self.completed else 'target_not_reached')
        except Exception as exc:
            with self.lock:
                if epoch == self.epoch:
                    self.active = False
                    self.elapsed = time.monotonic() - self.started_at
                    self.status = 'error'
                    self.error = '심층 분석 오류: ' + str(exc)
        finally:
            for key, value in saved_eval.items():
                setattr(evaluate, key, value)
            self.search_gate.release()

    def _worker(self, minimum, maximum, seconds, multipv, options, epoch, fen, snapshot, automatic):
        interrupted = threading.Event()

        def cancelled():
            return epoch != self.epoch or interrupted.is_set()

        acquired = acquire_search(self.search_gate, AUTO if automatic else MANUAL,
                                  interrupted, cancelled, self.search_wait_seconds)
        if not acquired:
            with self.lock:
                if epoch == self.epoch:
                    self.active = False
                    self.status = 'busy'
                    self.error = '다른 분석이 실행 중이에요. 잠시 후 다시 시도해 주세요.'
            return
        eval_keys = ('ATTACK_ACTIVITY', 'INITIATIVE', 'KING_SAFETY')
        saved_eval = {key: getattr(evaluate, key) for key in eval_keys}
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
            worker.selective = options['selective']
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

            evidence_cache = {}

            def format_line(info, rank):
                # FEN, SAN and score are all from the same completed depth.
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
                from sacrifice import candidate_evidence
                first = info.pv[0].uci() if info.pv else None
                if first and first not in evidence_cache:
                    try:
                        evidence_cache[first] = candidate_evidence(b, first)
                    except ValueError:
                        evidence_cache[first] = None
                return {
                    'sacrifice': evidence_cache.get(first),
                    'rank': rank,
                    'depth': info.depth,
                    'nodes': info.nodes,
                    'seconds': round(info.seconds, 3),
                    'score': info.score if turn_white else -info.score,
                    'pv': [m.uci() for m in info.pv],
                    'pv_san': pv_san,
                    'best_san': pv_san[0] if pv_san else None,
                }

            def publish(lines):
                if not lines:
                    return
                if epoch != self.epoch:
                    return
                formatted = [format_line(info, rank) for rank, info in enumerate(lines, 1)]
                payload = dict(formatted[0])
                payload['candidates'] = formatted
                payload['nodes'] = max(line.nodes for line in lines)
                payload['seconds'] = round(max(line.seconds for line in lines), 3)
                with self.lock:
                    if epoch != self.epoch:
                        return
                    self.completed = payload
                    self.game_scores[len(self.moves)] = {
                        "ply": len(self.moves), "score": payload["score"],
                        "depth": payload["depth"], "multipv": multipv, "options": dict(options)}
                    self.iterations.append(payload)
                    self.elapsed = payload["seconds"]
                if self.on_update:
                    self.on_update(self.state())

            # MultiPV=1 uses the original root search unchanged. Other values
            # emit a depth only when *all* requested root lines are complete.
            worker.search(b, max_depth=maximum, min_depth=minimum,
                          time_limit=seconds,
                          multipv=multipv,
                          on_info=(lambda info: publish([info])) if multipv == 1 else None,
                          on_multipv=publish if multipv > 1 else None,
                          on_iteration=on_iteration, full_time=True,
                          cancel_check=cancelled)
            with self.lock:
                if epoch != self.epoch:
                    return
                self.active = False
                self.status = ('preempted' if interrupted.is_set() else
                               'target_not_reached' if
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
            for key, value in saved_eval.items():
                setattr(evaluate, key, value)
            self.search_gate.release()

    def _state_locked(self):
        b = self.board
        return {
            'board': [[b.board[sq(f, r)] for f in range(8)] for r in range(7, -1, -1)],
            'fen': b.fen(),
            'base_fen': self.base_fen,
            'side_to_move': 'white' if b.side == WHITE else 'black',
            'moves': list(self.moves),
            'game_moves': list(self.game_moves),
            'cursor': len(self.moves),
            'game_scores': list(self.game_scores.values()),
            'tags': dict(self.tags),
            'legal': [m.uci() for m in b.legal_moves()],
            'check': sq_name(b.king_sq[b.side]) if b.in_check() else None,
            'outcome': b.outcome(),
            'epoch': self.epoch,
            'active': self.active,
            'automatic': self.mode == 'auto',
            'status': self.status,
            'error': self.error,
            'min_depth': self.min_depth,
            'max_depth': self.max_depth,
            'seconds': self.seconds,
            'multipv': self.multipv,
            'options': dict(self.options),
            'attempting': self.attempting,
            'deep': self.deep,
            'completed': dict(self.completed) if self.completed else None,
            'iterations': list(self.iterations),
            'elapsed': round(time.monotonic() - self.started_at, 2) if self.active and self.started_at else round(self.elapsed, 2),
            'version': VERSION,
        }

    def state(self):
        with self.lock:
            return self._state_locked()
