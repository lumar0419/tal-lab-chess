"""
uci.py — 4단계: UCI 프로토콜

체스 GUI(Arena, Cute Chess, BanksiaGUI …)나 lichess-bot은 엔진과 'UCI'라는 텍스트 규약으로
대화합니다. 엔진은 표준 입력으로 명령을 한 줄씩 받고, 표준 출력으로 답합니다.

  GUI → 엔진                                   엔진 → GUI
  uci                                          id name … / id author … / option … / uciok
  isready                                      readyok
  setoption name Hash value 64
  ucinewgame
  position startpos moves e2e4 e7e5
  go wtime 60000 btime 60000 winc 1000 binc 1000
                                               info depth 5 score cp 35 nodes 22117 nps 50283 time 440 pv b1c3 …
                                               bestmove b1c3
  stop / quit

실행:  python uci.py      (GUI의 '엔진 추가'에 이 명령 또는 engine.bat / engine.sh 를 등록)

구조
  · 명령 읽기는 메인 스레드, 탐색은 별도 스레드 → 탐색 중에도 stop·isready에 바로 답함
  · go infinite / go ponder 는 탐색이 먼저 끝나도 stop(또는 ponderhit)이 올 때까지 bestmove를 보내지 않음 (UCI 규정)
  · 이미 끝난 국면(메이트·자동 무승부)이면 bestmove 0000
  · 무승부 청구는 하지 않음: UCI에서는 GUI가 판정함
  · 엔진 출력은 ASCII 영어만 사용 (GUI마다 문자 인코딩이 달라서). 설명 주석만 한국어.
  · 잘못된 명령·FEN·수가 와도 죽지 않고 'info string'으로 알린 뒤 계속 동작

v0.4.1
  · go searchmoves (루트 후보 제한), go nodes (정확히 그 노드 수), ponder / ponderhit
  · 옵션: Hash(MB) → TT 용량 (1MB당 4000항목, 실측 기반 근사), Clear Hash, Move Overhead, Ponder,
          KingSafety (평가의 킹 안전 항목 켬/끔. 기본값 끔 — 대국 실험에서 켠 쪽이 약했음, evaluate.py 참고)
  · 디버그 명령: d (보드), eval (평가 내역), perft N, hashinfo (TT 용량·항목 수)
"""

import contextlib
import io
import sys
import threading
import time

from board import Board, START_FEN
from search import Searcher, TimeUp, uci_score, MAX_PLY, ENGINE_VERSION

ENGINE_NAME = "MyEngine"          # GUI에 보일 이름 — 마음대로 바꾸세요
ENGINE_AUTHOR = "MyEngine author"
UCI_VERSION = ENGINE_VERSION             # UCI 버전 (0.4.2: 평가 최적화·King Safety 개정. 프로토콜은 0.4.1과 같음)

# Hash(MB) → TT 용량(항목 수). 근사값임 (v0.4.1에서 실측해 정함).
#   파이썬 TT 항목 1개 = 튜플 + 해시 int + 점수 int + Move 객체 ≈ 220바이트, 칸 배열 8바이트
#   → 1MB당 4000개면 TT가 꽉 차도 약 0.9MB (bench/tt_mem.py: Hash 4MB, 98% 채움 → 3.35MB).
#   Hash는 TT만의 한도이고, 파이썬 인터프리터·보드·히스토리 표 등 나머지 메모리는 포함하지 않음.
TT_ENTRIES_PER_MB = 4000
DEFAULT_HASH_MB = 64
# Selective search remains available explicitly while tactical regressions are evaluated.
DEFAULT_SELECTIVE = False
DEFAULT_MOVE_OVERHEAD_MS = 50     # GUI·운영체제 지연을 감안해 남겨 두는 시간


def ascii_safe(text):
    """GUI로 나가는 글은 ASCII만 (한국어 오류 메시지 등이 인코딩 문제를 일으키지 않게)"""
    return str(text).encode('ascii', 'replace').decode('ascii')


def copy_board(b):
    """대국 기록(반복 판정용)까지 포함한 독립 복사본. 탐색은 복사본에서 하므로,
    탐색 중에 메인 스레드가 원래 보드를 읽거나(d, eval) 바꿔도 서로 영향이 없음."""
    c = Board()
    c.restore(b.snapshot())
    return c


class UCISearcher(Searcher):
    """Searcher에 '외부 정지 신호'만 더한 것. search.py는 손대지 않음.
    Searcher.search()는 시작할 때 stop_requested를 False로 되돌리므로, go 직후 바로 stop이
    오면 신호가 사라질 수 있음 → 스레드 안전한 Event로 따로 확인."""

    def __init__(self, tt_size):
        super().__init__(tt_size=tt_size)
        self.stop_event = threading.Event()
        self.pending_time = None     # ponderhit의 시각과 예산, 탐색 스레드가 직접 적용

    def _check_limits(self):
        if self.stop_event.is_set():
            raise TimeUp
        pending = self.pending_time
        if pending is not None:
            self.pending_time = None  # 탐색 스레드 안에서 적용하므로 search() 시작과 경쟁하지 않음
            started, budget = pending
            self.start, self.deadline = started, started + budget
        super()._check_limits()

    def _check_interval(self):
        # A pending ponderhit must be seen even when this pass started untimed.
        return 128 if self.deadline is None else super()._check_interval()


def allocate_time(clock_ms, inc_ms, movestogo, overhead_ms):
    """시계 정보로 이번 수의 최대 생각 시간(초)을 정함.
    · 남은 시간을 (남은 수 또는 30수)로 나누고 증가 시간의 3/4을 더함
    · 어떤 경우에도 남은 시간의 40%를 넘지 않음 (시간패 방지)
    탐색은 이 시간이 다 되면 멈추고, 절반이 지난 뒤에는 다음 깊이를 시작하지 않음."""
    remaining = max(clock_ms - overhead_ms, 1)
    moves_left = movestogo if movestogo and movestogo > 0 else 30
    target = remaining / moves_left + 0.75 * (inc_ms or 0)
    target = min(target, 0.4 * remaining)
    return max(target, 5) / 1000


def parse_go(tokens):
    """'go' 뒤의 토큰들을 사전으로. 모르는 토큰은 무시."""
    ints = {'wtime', 'btime', 'winc', 'binc', 'movestogo', 'depth', 'nodes', 'movetime', 'mate'}
    params, i = {}, 0
    while i < len(tokens):
        t = tokens[i]
        if t in ints and i + 1 < len(tokens):
            try:
                params[t] = int(tokens[i + 1])
            except ValueError:
                pass
            i += 2
        elif t in ('infinite', 'ponder'):
            params[t] = True
            i += 1
        elif t == 'searchmoves':           # 뒤따르는 수들을 다음 키워드 전까지 모음
            moves = []
            i += 1
            while i < len(tokens) and tokens[i] not in ints | {'infinite', 'ponder', 'searchmoves'}:
                moves.append(tokens[i])
                i += 1
            params['searchmoves'] = moves
        else:
            i += 1
    return params


class UCIEngine:
    def __init__(self, out=None):
        self.out = out or sys.stdout
        self.out_lock = threading.Lock()
        self.hash_mb = DEFAULT_HASH_MB
        self.move_overhead = DEFAULT_MOVE_OVERHEAD_MS
        self.searcher = UCISearcher(tt_size=self.hash_mb * TT_ENTRIES_PER_MB)
        self.searcher.selective = DEFAULT_SELECTIVE
        self.selective_option = DEFAULT_SELECTIVE   # TacticalSearch를 끌 때 되돌릴 값
        self.multipv = 1
        self.board = Board()
        self.position_key = (START_FEN, [])     # 마지막 position 명령 (수 목록 재사용용)
        self.thread = None
        # infinite·ponder 탐색은 탐색이 먼저 끝나도 이 신호가 올 때까지 bestmove를 보류
        # (stop → 둘 다 / ponderhit → 이것만 켬. 탐색 중단 신호는 searcher.stop_event)
        self.release = threading.Event()
        self.ponder_params = None               # go ponder 의 시계 정보 (ponderhit 때 시간 계산용)
        self.last_pv = []

    # ──────────────────────────── 출력 ────────────────────────────
    def send(self, line):
        with self.out_lock:                     # 탐색 스레드와 메인 스레드가 동시에 쓰지 않게
            try:
                self.out.write(line + '\n')
            except UnicodeEncodeError:          # 출력 인코딩이 한국어를 못 쓰는 환경 (디버그 출력 등)
                self.out.write(ascii_safe(line) + '\n')
            self.out.flush()

    def on_info(self, info, rank=None):
        ms = int(info.seconds * 1000)
        nps = int(info.nodes / info.seconds) if info.seconds > 0 else 0
        if rank is None or rank == 1:
            self.last_pv = list(info.pv)
        pv = ' '.join(m.uci() for m in info.pv)
        multipv = f' multipv {rank}' if rank is not None else ''
        self.send(f"info depth {info.depth}{multipv} score {uci_score(info.score)} nodes {info.nodes} "
                  f"nps {nps} time {ms} pv {pv}")

    def on_multipv(self, group):
        for rank, info in enumerate(group, 1):
            self.on_info(info, rank)

    # ──────────────────────────── 명령 처리 ────────────────────────────
    def handle(self, line):
        """명령 한 줄 처리. quit이면 False."""
        tokens = line.split()
        if not tokens:
            return True
        cmd, args = tokens[0], tokens[1:]
        try:
            if cmd == 'uci':
                self.send(f"id name {ENGINE_NAME} {UCI_VERSION}")
                self.send(f"id author {ENGINE_AUTHOR}")
                self.send(f"option name Hash type spin default {DEFAULT_HASH_MB} min 1 max 1024")
                self.send("option name MultiPV type spin default 1 min 1 max 5")
                self.send("option name Clear Hash type button")
                self.send(f"option name Move Overhead type spin default {DEFAULT_MOVE_OVERHEAD_MS} "
                          f"min 0 max 5000")
                self.send("option name TacticalChecks type check default false")
                self.send("option name PVS type check default true")
                self.send("option name Aspiration type check default false")
                self.send("option name TacticalOrdering type check default false")
                self.send("option name LMR type check default false")
                self.send("option name CheckContinuation type check default false")
                self.send("option name CheckExtensionLimit type spin default -1 min -1 max 10")
                self.send("option name ExperimentalNullMove type check default false")
                self.send("option name ExperimentalNullThreat type check default false")
                self.send(f"option name SelectiveSearch type check default {str(DEFAULT_SELECTIVE).lower()}")
                self.send("option name TacticalSearch type check default false")
                self.send("option name AttackActivity type check default false")
                self.send("option name Initiative type check default false")
                self.send("option name Ponder type check default false")   # 상대 차례에 미리 생각 (v0.4.1)
                import evaluate                 # 기본값은 evaluate.KING_SAFETY 한 곳에서 정함
                self.send(f"option name KingSafety type check default {str(evaluate.KING_SAFETY).lower()}")
                self.send("uciok")
            elif cmd == 'isready':
                self.send("readyok")            # 탐색 중에도 바로 답함
            elif cmd == 'setoption':
                self.cmd_setoption(args)
            elif cmd == 'ucinewgame':
                self.stop_search()
                self.searcher.tt.clear()
                self.board = Board()
                self.position_key = (START_FEN, [])
            elif cmd == 'position':
                self.stop_search()
                self.cmd_position(args)
            elif cmd == 'go':
                self.stop_search()
                self.cmd_go(args)
            elif cmd == 'stop':                 # 탐색을 멈추고 지금까지의 최선수를 냄
                self.stop_search()
            elif cmd == 'ponderhit':            # 예상한 수를 상대가 둠: 같은 탐색을 이어서, 이제부터 시간 제한
                self.cmd_ponderhit()
            elif cmd == 'quit':
                self.stop_search()
                return False
            # ── 사람용 디버그 명령 (GUI는 보내지 않음) ──
            elif cmd == 'd':
                self.send(str(self.board))
                self.send(f"Fen: {self.board.fen()}")
                self.send(f"Key: {self.board.hash:016x}")
            elif cmd == 'eval':                 # 평가 내역 + King Safety 끔/켬 차이 (항목별)
                from evaluate import explain, explain_king_safety
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    explain(self.board)
                    explain_king_safety(self.board, "King Safety off -> on")
                for ln in buf.getvalue().splitlines():
                    self.send(ln)
            elif cmd == 'hashinfo':             # TT 상태 (v0.4.1): Hash 설정, 용량, 저장된 항목 수
                tt = self.searcher.tt
                self.send(f"info string hash_mb {self.hash_mb} capacity {tt.capacity} "
                          f"entries {len(tt)} generation {tt.generation}")
            elif cmd == 'perft' and args:
                from perft import perft
                t0 = time.time()
                n = perft(self.board, int(args[0]))
                self.send(f"Nodes searched: {n}  ({time.time() - t0:.2f}s)")
            elif cmd == 'debug':
                pass                            # debug on/off: 받아들이되 아무것도 안 함
            else:
                self.send(f"info string unknown command: {line[:80]}")
        except Exception as e:                  # 어떤 입력이 와도 엔진은 죽지 않음
            self.send(f"info string error in '{ascii_safe(cmd)}': {type(e).__name__}")
        return True

    def cmd_setoption(self, args):
        if 'name' not in args:
            return
        i = args.index('name')
        if 'value' in args:
            j = args.index('value')
            name, value = ' '.join(args[i + 1:j]).lower(), ' '.join(args[j + 1:])
        else:
            name, value = ' '.join(args[i + 1:]).lower(), None
        if name == 'hash' and value is not None:
            self.stop_search()
            self.hash_mb = max(1, min(1024, int(value)))
            self.searcher.tt_size = self.hash_mb * TT_ENTRIES_PER_MB   # 고정 크기 TT를 새로 만듦 (내용 비움)
        elif name == 'clear hash':
            self.stop_search()
            self.searcher.tt.clear()
        elif name == 'multipv' and value is not None:
            self.stop_search()
            self.multipv = max(1, min(5, int(value)))
        elif name == 'move overhead' and value is not None:
            self.move_overhead = max(0, min(5000, int(value)))
        elif name == 'ponder':
            pass                                # GUI가 go ponder 를 보낼지 정하는 표시일 뿐
        elif name == 'aspiration' and value is not None:
            self.stop_search()
            enabled = value.strip().lower() == 'true'
            if enabled != self.searcher.aspiration:
                self.searcher.aspiration = enabled
                self.searcher.tt.clear()  # separate experiment conditions
        elif name == 'pvs' and value is not None:
            self.stop_search()
            enabled = value.strip().lower() == 'true'
            if enabled != self.searcher.pvs:
                self.searcher.pvs = enabled
                self.searcher.tt.clear()       # 변경 직후 독립적인 검색 경로로 성능 재측정
        elif name == 'tacticalordering' and value is not None:
            self.stop_search()
            enabled = value.strip().lower() == 'true'
            if enabled != self.searcher.tactical_ordering:
                self.searcher.tactical_ordering = enabled
                self.searcher.tt.clear()  # clear state for a controlled comparison
        elif name == 'lmr' and value is not None:
            self.stop_search()
            enabled = value.strip().lower() == 'true'
            if enabled != self.searcher.lmr:
                self.searcher.lmr = enabled
                self.searcher.tt.clear()  # do not mix reduced and full-depth entries
        elif name == 'checkcontinuation' and value is not None:
            self.stop_search()
            enabled = value.strip().lower() == 'true'
            if enabled != self.searcher.check_continuation:
                self.searcher.check_continuation = enabled
                self.searcher.tt.clear()  # qsearch meaning changes
        elif name == 'checkextensionlimit' and value is not None:
            self.stop_search()
            limit = max(-1, min(10, int(value)))
            self.searcher.check_extension_limit = None if limit == -1 else limit
        elif name in ('experimentalnullmove', 'experimentalnullthreat') and value is not None:
            self.stop_search()
            attr = 'null_move_pruning' if name == 'experimentalnullmove' else 'null_threat_extension'
            setattr(self.searcher, attr, value.strip().lower() == 'true')
        elif name == 'selectivesearch' and value is not None:
            self.stop_search()                  # 설정이 바뀌면 다음 탐색 시작 때 TT를 비움 (search.py)
            self.selective_option = value.strip().lower() == 'true'
            self.searcher.selective = self.selective_option or self.searcher.tactical
        elif name == 'tacticalsearch' and value is not None:
            # v0.9.3 전술 프로필: 선택적 탐색 + 희생 수 연장. 끄면 SelectiveSearch 설정으로 돌아감.
            self.stop_search()
            self.searcher.set_tactical(value.strip().lower() == 'true')
            if not self.searcher.tactical:
                self.searcher.selective = self.selective_option
        elif name == 'tacticalchecks' and value is not None:
            self.stop_search()                        # 평가 방식이 바뀌므로 진행 중 탐색 중단
            enabled = value.strip().lower() == 'true'
            if enabled != self.searcher.qsearch_quiet_checks:
                self.searcher.qsearch_quiet_checks = enabled
                self.searcher.tt.clear()               # 서로 다른 qsearch 결과 재사용 금지
        elif name == 'attackactivity' and value is not None:
            self.stop_search()
            import evaluate
            enabled = value.strip().lower() == 'true'
            if enabled != evaluate.ATTACK_ACTIVITY:
                evaluate.ATTACK_ACTIVITY = enabled
                self.searcher.tt.clear()     # 평가 설정이 달라지면 TT 점수 재사용 불가
        elif name == 'initiative' and value is not None:
            self.stop_search()
            import evaluate
            enabled = value.strip().lower() == 'true'
            if enabled != evaluate.INITIATIVE:
                evaluate.INITIATIVE = enabled
                self.searcher.tt.clear()  # 평가 기준 변경: 이전 점수 재사용 금지
        elif name == 'kingsafety' and value is not None:
            self.stop_search()                  # 탐색 중에 평가가 바뀌지 않게
            import evaluate
            evaluate.KING_SAFETY = value.strip().lower() == 'true'
            self.searcher.tt.clear()            # 다른 평가로 저장한 점수를 다시 쓰지 않게
        else:
            self.send(f"info string unsupported option: {name}")

    def cmd_position(self, args):
        if not args:
            return
        if args[0] == 'startpos':
            fen, rest = START_FEN, args[1:]
        elif args[0] == 'fen':
            if 'moves' in args:
                k = args.index('moves')
                fen, rest = ' '.join(args[1:k]), args[k:]
            else:
                fen, rest = ' '.join(args[1:]), []
        else:
            self.send("info string position: expected 'startpos' or 'fen'")
            return
        moves = rest[1:] if rest and rest[0] == 'moves' else []

        # GUI는 매 수마다 처음부터 전체 수 목록을 보냄 → 앞부분이 같으면 이어서 두기만 함
        old_fen, old_moves = self.position_key
        if fen == old_fen and moves[:len(old_moves)] == old_moves and len(self.board.history) == len(old_moves):
            board, start = self.board, len(old_moves)
        else:
            try:
                board = Board(fen)
            except ValueError:
                self.send(f"info string invalid fen, position unchanged: {ascii_safe(fen)}")
                return
            start = 0
        for k in range(start, len(moves)):
            m = board.parse_uci(moves[k])
            if m is None:
                self.send(f"info string illegal move '{ascii_safe(moves[k])}', ignoring it and the rest")
                moves = moves[:k]
                break
            board.make_move(m)
        self.board = board
        self.position_key = (fen, list(moves))

    def time_for_move(self, p, board):
        """go 매개변수 → (이번 수의 시간 제한 초, 수가 하나뿐인가)"""
        if 'movetime' in p:
            return max(p['movetime'] - self.move_overhead, 5) / 1000, False
        side = 'w' if board.side == 0 else 'b'
        if f'{side}time' in p:
            limit = allocate_time(p[f'{side}time'], p.get(f'{side}inc', 0), p.get('movestogo'),
                                  self.move_overhead)
            return limit, len(board.legal_moves()) == 1
        return None, False

    def cmd_go(self, args):
        p = parse_go(args)
        pondering = bool(p.get('ponder'))
        infinite = bool(p.get('infinite')) or pondering
        max_depth = p.get('depth') or (2 * p['mate'] if p.get('mate') else MAX_PLY)
        node_limit = p.get('nodes')
        time_limit, only_move = self.time_for_move(p, self.board)
        if only_move and not pondering:
            max_depth = 1                       # 둘 수가 하나뿐이면 생각하지 않고 바로
        if not infinite and time_limit is None and node_limit is None and max_depth == MAX_PLY:
            infinite = True                     # 조건 없는 'go'는 stop이 올 때까지 (Stockfish와 같게)
        if infinite:
            time_limit = None                   # infinite·ponder는 시간 제한 없음
        self.ponder_params = p if pondering else None

        root_moves = None
        if 'searchmoves' in p:
            root_moves = p['searchmoves']
            legal = {m.uci() for m in self.board.legal_moves()}
            bad = [u for u in root_moves if u.lower() not in legal]
            if bad:
                self.send(f"info string searchmoves: ignoring illegal {ascii_safe(' '.join(bad))}")
            if not any(u.lower() in legal for u in root_moves):
                self.send("info string searchmoves: no legal candidate")

        self.searcher.stop_event.clear()
        self.searcher.pending_time = None
        self.release.clear()
        self.last_pv = []
        board = copy_board(self.board)          # 탐색은 복사본에서
        self.thread = threading.Thread(target=self._search_worker,
                                       args=(board, max_depth, time_limit, node_limit, infinite, root_moves),
                                       daemon=True)
        self.thread.start()

    def cmd_ponderhit(self):
        """상대가 예상대로 둠. 지금 돌고 있는 탐색(쌓인 결과·TT 그대로)에 이 순간부터 시간 제한을 걸어 계속함."""
        started = time.monotonic()
        p = self.ponder_params
        self.ponder_params = None
        if not (self.thread and self.thread.is_alive()) or p is None:
            self.release.set()
            return
        if p.get('infinite'):                   # go ponder infinite: ponderhit 뒤에도 stop까지 계속 (UCI)
            return
        limit, _ = self.time_for_move(p, self.board)
        if limit is not None:
            self.searcher.pending_time = started, limit
        self.release.set()                      # 탐색이 이미 끝나 기다리는 중이면 바로 bestmove

    def _search_worker(self, board, max_depth, time_limit, node_limit, infinite, root_moves):
        best, score = None, 0
        t0 = time.time()
        try:
            multipv = self.multipv
            best, score = self.searcher.search(board, max_depth=max_depth, time_limit=time_limit,
                                               node_limit=node_limit, multipv=multipv,
                                               on_info=self.on_info if multipv == 1 else None,
                                               on_multipv=self.on_multipv if multipv > 1 else None,
                                               root_moves=root_moves)
        except Exception as e:                  # 탐색 오류가 나도 GUI에는 반드시 수를 돌려줌
            self.send(f"info string search error: {type(e).__name__}")
            moves = board.legal_moves()
            best = moves[0] if moves else None
        if infinite:
            self.release.wait()                 # infinite·ponder: stop(또는 ponderhit) 전에는 bestmove 보류
        elapsed = max(time.time() - t0, 1e-6)
        self.send(f"info nodes {self.searcher.nodes} nps {int(self.searcher.nodes / elapsed)} "
                  f"time {int(elapsed * 1000)}")
        if best is None:                        # 이미 끝난 국면, 또는 searchmoves에 합법 후보 없음
            self.send(f"info depth 0 score {uci_score(score)}")
            self.send("bestmove 0000")
        else:
            pv = self.last_pv
            ponder = f" ponder {pv[1].uci()}" if len(pv) >= 2 and pv[0] == best else ""
            self.send(f"bestmove {best.uci()}{ponder}")

    def stop_search(self):
        """탐색 스레드를 멈추고 끝날 때까지 기다림 → 그 뒤에만 다음 명령이 Searcher를 건드림"""
        if self.thread and self.thread.is_alive():
            self.searcher.stop_event.set()
            self.release.set()
            self.thread.join()
        self.thread = None
        self.ponder_params = None


def main():
    # GUI는 ASCII만 보내지만, 사람이 콘솔에서 한국어를 치거나 콘솔 인코딩이 달라도 죽지 않게
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass
    engine = UCIEngine()
    while True:
        line = sys.stdin.readline()
        if not line:                            # 입력이 닫힘 (GUI 종료) → 끝냄
            engine.stop_search()
            break
        if not engine.handle(line.strip()):
            break


if __name__ == '__main__':
    main()
