"""
test_uci.py — 4단계 UCI 프로토콜 테스트

  python test_uci.py

엔진(uci.py)을 별도 프로세스로 띄워 GUI처럼 명령을 보내고, 응답 내용과 응답 시간을 확인합니다.
python-chess(pip install chess)가 있으면 python-chess의 UCI 클라이언트로 실제 시간제 대국도 둡니다
(없으면 '건너뜀', 통과로 세지 않음). 엔진 자체는 python-chess가 필요 없습니다.
"""

import os
import queue
import re
import subprocess
import sys
import threading
import time

from board import Board

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_CMD = [sys.executable, os.path.join(HERE, 'uci.py')]
RESULTS, SKIPPED = [], []
INFO_RE = re.compile(r"^info depth \d+ score (cp -?\d+|mate -?\d+) nodes \d+ nps \d+ time \d+ pv( [a-h][1-8][a-h][1-8][qrbn]?)+$")


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond)))
    print(f"  [{'OK  ' if cond else '실패'}] {name}" + (f"  ({detail})" if detail else ''))


def skip(name, reason):
    SKIPPED.append(name)
    print(f"  [건너뜀] {name}  ({reason})")


def section(title):
    print(f"\n■ {title}")


class Engine:
    """엔진 프로세스와 줄 단위로 주고받는 도우미 (GUI 역할)"""

    def __init__(self, env=None):
        self.p = subprocess.Popen(ENGINE_CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=HERE,
                                  env=env)
        self.q = queue.Queue()
        self.lines = []
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.p.stdout:
            self.q.put(line.rstrip('\n'))
        self.q.put(None)

    def send(self, line):
        self.p.stdin.write(line + '\n')
        self.p.stdin.flush()

    def wait_for(self, pred, timeout):
        """조건을 만족하는 줄이 나올 때까지 읽음 → (그 줄, 그동안 읽은 줄들, 걸린 시간)"""
        t0 = time.time()
        got = []
        while True:
            left = timeout - (time.time() - t0)
            if left <= 0:
                return None, got, time.time() - t0
            try:
                line = self.q.get(timeout=left)
            except queue.Empty:
                return None, got, time.time() - t0
            if line is None:
                return None, got, time.time() - t0
            got.append(line)
            self.lines.append(line)
            if pred(line):
                return line, got, time.time() - t0

    def bestmove(self, timeout):
        line, got, dt = self.wait_for(lambda l: l.startswith('bestmove'), timeout)
        return (line.split()[1] if line else None), got, dt

    def close(self):
        try:
            self.send('quit')
        except Exception:
            pass
        try:
            self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.p.kill()


def legal_after(fen, moves, mv):
    b = Board(fen)
    for m in moves:
        b.push_uci(m)
    return b.parse_uci(mv) is not None


START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'


def test_handshake_and_basic():
    section("핸드셰이크와 기본 탐색")
    e = Engine()
    e.send('uci')
    line, got, dt = e.wait_for(lambda l: l == 'uciok', 5)
    check("uci → id name / id author / option / uciok", line == 'uciok'
          and any(l.startswith('id name ') for l in got) and any(l.startswith('id author ') for l in got)
          and any(l.startswith('option name Hash') for l in got), f"{dt:.2f}s")
    e.send('isready')
    line, _, dt = e.wait_for(lambda l: l == 'readyok', 2)
    check("isready → readyok", line == 'readyok', f"{dt * 1000:.0f}ms")

    e.send('ucinewgame')
    e.send('position startpos moves e2e4 e7e5')
    e.send('go depth 4')
    mv, got, dt = e.bestmove(30)
    infos = [l for l in got if l.startswith('info depth')]
    depths = [int(l.split()[2]) for l in infos]
    check("go depth 4: info 줄 형식이 UCI 규격, 깊이 1→4 순서, bestmove는 합법수",
          mv and legal_after(START, ['e2e4', 'e7e5'], mv) and depths == [1, 2, 3, 4]
          and all(INFO_RE.match(l) for l in infos), f"{mv}, {infos[-1] if infos else ''}")

    e.send('position fen 7k/8/6K1/8/8/8/8/R7 w - - 0 1')
    e.send('go depth 3')
    mv, got, _ = e.bestmove(10)
    check("메이트 1수: bestmove a1a8, 'score mate 1'", mv == 'a1a8' and any('score mate 1 ' in l for l in got))
    e.close()


def test_time_controls():
    section("시간 관리")
    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    e.send('position startpos')
    e.send('go movetime 500')
    mv, _, dt = e.bestmove(5)
    check("go movetime 500: 500ms 안에 bestmove", mv and dt <= 0.6, f"{dt * 1000:.0f}ms")
    e.send('position startpos moves e2e4')
    e.send('go wtime 3000 btime 3000 winc 0 binc 0')
    mv, _, dt = e.bestmove(5)
    check("go btime 3000 (흑 차례, 남은 3초): 짧게 생각 (≤ 남은 시간의 10%)", mv and dt <= 0.3, f"{dt * 1000:.0f}ms")
    e.send('position startpos')
    e.send('go wtime 120 btime 120')
    mv, _, dt = e.bestmove(5)
    check("go wtime 120 (시간 거의 없음): 그래도 합법수를 빨리", mv and legal_after(START, [], mv) and dt <= 0.15,
          f"{dt * 1000:.0f}ms")
    e.send('position startpos')
    e.send('go nodes 3000')
    mv, got, dt = e.bestmove(10)
    check("go nodes 3000: 노드 한도로 끝남", mv is not None and dt < 2, f"{dt:.2f}s")
    e.send('position fen 7k/8/8/8/8/8/1q6/K7 w - - 0 1')       # 체크, 합법수는 Kxb2 하나뿐
    e.send('go wtime 60000 btime 60000')
    mv, _, dt = e.bestmove(5)
    check("시계 대국에서 둘 수 있는 수가 하나뿐이면 바로 둠 (보통은 2초 정도 생각할 시간)",
          len(Board('7k/8/8/8/8/8/1q6/K7 w - - 0 1').legal_moves()) == 1 and mv == 'a1b2' and dt < 0.2,
          f"{dt * 1000:.0f}ms")
    e.close()


def test_stop_infinite():
    section("stop / infinite / isready")
    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    e.send('position fen 7k/8/6K1/8/8/8/8/R7 w - - 0 1')       # 메이트를 금방 찾는 국면
    e.send('go infinite')
    line, got, _ = e.wait_for(lambda l: l.startswith('bestmove'), 1.0)
    check("go infinite: 메이트를 찾아도 stop 전에는 bestmove를 보내지 않음", line is None
          and any('score mate 1' in l for l in got))
    e.send('isready')
    line, _, dt = e.wait_for(lambda l: l == 'readyok', 1)
    check("탐색 중 isready에 즉시 readyok", line == 'readyok', f"{dt * 1000:.0f}ms")
    e.send('stop')
    mv, _, dt = e.bestmove(2)
    check("stop → bestmove a1a8 즉시", mv == 'a1a8' and dt < 0.3, f"{dt * 1000:.0f}ms")

    e.send('position startpos')
    e.send('go infinite')
    time.sleep(1.5)
    e.send('stop')
    mv, _, dt = e.bestmove(2)
    check("시작 국면 infinite 1.5초 후 stop → 0.3초 안에 합법 bestmove", mv and legal_after(START, [], mv)
          and dt < 0.3, f"{mv} {dt * 1000:.0f}ms")
    e.send('position startpos')
    e.send('go infinite')
    e.send('stop')                                          # go 직후 바로 stop (경쟁 상태)
    mv, _, dt = e.bestmove(2)
    check("go 직후 바로 stop해도 멈추고 합법수를 냄", mv and legal_after(START, [], mv), f"{dt * 1000:.0f}ms")
    e.send('position startpos')
    e.send('go')                                            # 조건 없는 go = infinite
    line, _, _ = e.wait_for(lambda l: l.startswith('bestmove'), 0.8)
    e.send('stop')
    mv, _, _ = e.bestmove(2)
    check("조건 없는 'go'는 stop까지 계속", line is None and mv is not None)
    e.send('go infinite')
    t0 = time.time()
    e.send('quit')
    e.p.wait(timeout=3)
    check("탐색 중 quit → 프로세스 종료", e.p.returncode is not None, f"{time.time() - t0:.2f}s")


def test_terminal_and_history():
    section("끝난 국면, 대국 기록(반복) 전달")
    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    for fen, score, name in (("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", 'mate 0', '체크메이트'),
                             ("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 'cp 0', '스테일메이트'),
                             ("4k3/8/8/8/8/8/8/4K3 w - - 0 1", 'cp 0', '킹 대 킹')):
        e.send(f'position fen {fen}')
        e.send('go depth 3')
        mv, got, _ = e.bestmove(5)
        check(f"{name}: 'info depth 0 score {score}' + bestmove 0000",
              mv == '0000' and f'info depth 0 score {score}' in got)

    e.send('position fen 4k3/8/8/8/8/8/8/R3K3 w - - 0 1 moves e1d1 e8d7 d1e1 d7e8 e1d1 e8d7 d1e1')
    e.send('go depth 4')
    mv, got, _ = e.bestmove(10)
    last = [l for l in got if l.startswith('info depth')][-1]
    check("position의 수 목록이 반복 기록으로 이어짐: 룩 없는 흑이 Ke8(3회 반복 청구)로 0점",
          mv == 'd7e8' and ' score cp 0 ' in last, f"{mv}, {last[:40]}")

    import random
    rng = random.Random(3)
    b = Board()
    seq = []
    for _ in range(60):
        moves = b.legal_moves()
        if not moves or b.outcome():
            break
        m = rng.choice(moves)
        b.make_move(m)
        seq.append(m.uci())
    ok = True
    for k in range(1, len(seq) + 1, 7):                     # GUI처럼 매번 처음부터 전체 수 목록을 보냄
        e.send('position startpos moves ' + ' '.join(seq[:k]))
        e.send('d')
        line, _, _ = e.wait_for(lambda l: l.startswith('Fen: '), 3)
        ref = Board()
        for u in seq[:k]:
            ref.push_uci(u)
        ok &= line == f"Fen: {ref.fen()}"
    e.send('position startpos moves e2e4')                  # 앞부분이 다르면 새로 만듦
    e.send('d')
    line, _, _ = e.wait_for(lambda l: l.startswith('Fen: '), 3)
    check("position 수 목록을 이어 붙여 처리해도 FEN이 정확 (60수 대국, 새 대국 전환 포함)",
          ok and line == 'Fen: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1')
    e.close()


def test_robustness():
    section("잘못된 입력")
    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    for junk in ('hello', 'position', 'position fen', 'position fen 8/8/8 w', 'go depth', 'go depth abc wtime x',
                 'setoption', 'setoption name Hash value abc', 'setoption name Foo value 1', 'perft x',
                 'position startpos moves e2e4 e2e4 e7e5'):
        e.send(junk)
        if junk.startswith('go'):
            e.send('stop')
            e.bestmove(2)
    e.send('isready')
    line, got, _ = e.wait_for(lambda l: l == 'readyok', 3)
    check("잘못된 명령 11종 뒤에도 정상 응답 (죽지 않음)", line == 'readyok' and e.p.poll() is None)
    check("불법수가 섞인 position: 그 앞까지만 적용하고 알림", any("illegal move 'e2e4'" in l for l in got))
    e.send('d')
    line, _, _ = e.wait_for(lambda l: l.startswith('Fen: '), 3)
    check("  → 국면은 1.e4 까지", line == 'Fen: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1')
    e.send('setoption name Hash value 16')
    e.send('setoption name Clear Hash')
    e.send('setoption name Move Overhead value 100')
    e.send('position startpos')
    e.send('go depth 3')
    mv, _, _ = e.bestmove(10)
    check("setoption Hash / Clear Hash / Move Overhead 후 정상 탐색", mv is not None)
    e.close()

    env = dict(os.environ, PYTHONIOENCODING='ascii')         # 한국어를 못 쓰는 콘솔 흉내
    e = Engine(env=env)
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    e.send('eval')                                           # 한국어 디버그 출력
    e.send('position fen 잘못된 FEN')
    e.send('isready')
    line, got, _ = e.wait_for(lambda l: l == 'readyok', 3)
    check("ASCII 전용 출력 환경에서도 한국어 출력 때문에 죽지 않음", line == 'readyok' and e.p.poll() is None
          and not any('Traceback' in l for l in got))
    e.close()

    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    e.p.stdin.close()                                        # GUI가 갑자기 꺼짐
    try:
        e.p.wait(timeout=3)
        ended = True
    except subprocess.TimeoutExpired:
        ended = False
        e.p.kill()
    check("입력이 닫히면(GUI 종료) 엔진도 종료", ended)


def test_v041_searchmoves_nodes():
    section("v0.4.1  go searchmoves / go nodes")
    from search import Searcher
    e = Engine()
    e.send('uci')
    line, got, _ = e.wait_for(lambda l: l == 'uciok', 5)
    fen = 'r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10'
    cands = ['h2h3', 'a1d1', 'g5h4']
    e.send('ucinewgame')
    e.send(f'position fen {fen}')
    e.send('go depth 3 searchmoves ' + ' '.join(cands))
    mv, got, _ = e.bestmove(30)
    last = [l for l in got if l.startswith('info depth 3')][-1]
    ref_mv, ref_sc = Searcher().search(Board(fen), max_depth=3, on_info=None, root_moves=cands)
    check("searchmoves 3개: bestmove가 후보 안이고, 같은 조건의 직접 탐색과 수·점수가 같음",
          mv in cands and mv == ref_mv.uci() and f" score cp {ref_sc} " in last, f"{mv}, {last[:30]}")
    e.send(f'position fen {fen}')
    e.send('go depth 2 searchmoves h2h3 e1e8 zz')
    mv, got, _ = e.bestmove(10)
    check("불법·잘못된 후보는 알리고 무시 → 남은 합법 후보(h2h3)",
          mv == 'h2h3' and any('ignoring illegal e1e8 zz' in l for l in got))
    e.send(f'position fen {fen}')
    e.send('go depth 2 searchmoves e1e8')
    mv, got, _ = e.bestmove(10)
    check("합법 후보가 없으면 알리고 bestmove 0000",
          mv == '0000' and any('no legal candidate' in l for l in got))
    e.send('position startpos')
    e.send('go infinite searchmoves a2a3 b2b3')
    time.sleep(0.5)
    e.send('stop')
    mv, _, _ = e.bestmove(3)
    check("go infinite searchmoves + stop: 후보 안에서 답함", mv in ('a2a3', 'b2b3'), mv)

    for lim in (777, 5000):
        e.send('position startpos moves e2e4 e7e5')
        e.send(f'go nodes {lim}')
        mv, got, _ = e.bestmove(10)
        n = [int(l.split()[2]) for l in got if l.startswith('info nodes ')]
        check(f"go nodes {lim}: 최종 노드 수가 정확히 {lim}", n == [lim] and mv is not None, f"{n}")
    e.close()


def test_v041_stop_races():
    section("v0.4.1  stop·시간 동시 발생, bestmove는 go마다 정확히 한 번")
    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)
    for k in range(5):
        e.send('position startpos')
        e.send('go movetime 100')
        e.send('stop')                          # 시간 제한과 stop이 거의 동시에
        e.bestmove(3)
    e.send('position startpos')
    e.send('go depth 3')
    mv, _, _ = e.bestmove(10)
    e.send('isready')
    e.wait_for(lambda l: l == 'readyok', 3)
    time.sleep(0.3)
    count = sum(l.startswith('bestmove') for l in e.lines)
    check("movetime 100 + 즉시 stop × 5 뒤 정상 탐색: bestmove 6번 (중복·누락 없음)", count == 6 and mv is not None,
          f"{count}번")
    e.close()


def test_v041_ponder():
    section("v0.4.1  Ponder (상대 차례에 미리 생각)")
    e = Engine()
    e.send('uci')
    line, got, _ = e.wait_for(lambda l: l == 'uciok', 5)
    check("Ponder 옵션을 광고함 (option name Ponder type check)", 'option name Ponder type check default false' in got)
    e.send('setoption name Ponder value true')
    e.send('position startpos moves e2e4 e7e5')            # GUI가 예상수 e7e5를 둔 국면에서 생각시킴
    e.send('go ponder wtime 3000 btime 3000 winc 0 binc 0')
    line, got, _ = e.wait_for(lambda l: l.startswith('bestmove'), 1.0)
    check("go ponder: 1초 동안 bestmove를 보내지 않음 (생각만 함)", line is None and any(l.startswith('info depth') for l in got))
    e.send('ponderhit')
    mv, got, dt = e.bestmove(3)
    check("ponderhit → 그 시점부터 이번 수의 시간(약 0.1초) 안에 bestmove", mv and dt < 0.4, f"{mv} {dt * 1000:.0f}ms")
    toks = got[-1].split()
    ok_ponder = True
    if len(toks) == 4 and toks[2] == 'ponder':
        ok_ponder = legal_after(START, ['e2e4', 'e7e5', toks[1]], toks[3])
    check("bestmove의 ponder 수는 그 수 다음 국면에서 합법", ok_ponder, got[-1])

    e.send('position startpos moves e2e4')
    e.send('go ponder wtime 3000 btime 3000')
    e.send('ponderhit')                                     # 탐색 스레드가 시작하기 전일 수도 있는 즉시 ponderhit
    mv, _, dt = e.bestmove(3)
    check("go ponder 직후 즉시 ponderhit해도 멈춤 (영원히 생각하지 않음)", mv is not None and dt < 0.5, f"{dt * 1000:.0f}ms")
    e.send('position startpos moves e2e4')
    e.send('go ponder wtime 3000 btime 3000')
    time.sleep(0.4)
    e.send('stop')                                          # 예상이 빗나감 → GUI가 stop
    mv, _, dt = e.bestmove(2)
    e.send('position startpos moves e2e4 c7c5')
    e.send('go wtime 3000 btime 3000')
    mv2, _, _ = e.bestmove(3)
    check("ponder 중 stop(예상 빗나감) → 바로 bestmove, 이어서 새 국면 탐색 정상",
          mv is not None and dt < 0.2 and mv2 and legal_after(START, ['e2e4', 'c7c5'], mv2))
    e.send('position fen 7k/8/6K1/8/8/8/8/R7 w - - 0 1')
    e.send('go ponder wtime 3000 btime 3000')
    line, _, _ = e.wait_for(lambda l: l.startswith('bestmove'), 0.8)
    e.send('ponderhit')
    mv, _, dt = e.bestmove(2)
    check("ponder 중 이미 메이트를 확정해 탐색이 끝났어도 ponderhit 전에는 보류, 후에는 즉시",
          line is None and mv == 'a1a8' and dt < 0.2)
    e.send('position fen 7k/8/6K1/8/8/8/8/R7 w - - 0 1')
    e.send('go ponder infinite')
    e.send('ponderhit')
    line, _, _ = e.wait_for(lambda l: l.startswith('bestmove'), 0.8)
    e.send('stop')
    mv, _, _ = e.bestmove(2)
    check("go ponder infinite: ponderhit 뒤에도 stop 전에는 bestmove를 보내지 않음",
          line is None and mv == 'a1a8')
    e.send('position startpos')
    e.send('go ponder wtime 3000 btime 3000')
    e.send('isready')
    line, _, _ = e.wait_for(lambda l: l == 'readyok', 1)
    e.send('quit')
    e.p.wait(timeout=3)
    check("ponder 중 isready 즉시 응답, quit으로 종료", line == 'readyok' and e.p.returncode is not None)


def test_v041_hash():
    section("v0.4.1  Hash 옵션이 TT 용량을 정함 / Clear Hash")
    import uci as uci_mod
    e = Engine()
    e.send('uci')
    e.wait_for(lambda l: l == 'uciok', 5)

    def info():
        e.send('hashinfo')
        line, _, _ = e.wait_for(lambda l: l.startswith('info string hash_mb '), 3)
        w = line.split() if line else []
        return {w[k]: int(w[k + 1]) for k in range(2, len(w) - 1, 2)} if line else {}

    per = uci_mod.TT_ENTRIES_PER_MB
    d0 = info()
    check(f"기본 Hash {uci_mod.DEFAULT_HASH_MB}MB → 용량 {uci_mod.DEFAULT_HASH_MB}×{per}, 처음엔 비어 있음",
          d0.get('hash_mb') == uci_mod.DEFAULT_HASH_MB and d0.get('capacity') == uci_mod.DEFAULT_HASH_MB * per
          and d0.get('entries') == 0, f"{d0}")
    e.send('setoption name Hash value 1')
    e.send('position startpos moves e2e4 e7e5 g1f3')
    e.send('go nodes 60000')
    mv, _, _ = e.bestmove(60)
    d1 = info()
    check(f"Hash 1 → 용량 {per}, 6만 노드 탐색 뒤에도 항목 수 <= 용량",
          mv is not None and d1.get('capacity') == per and 0 < d1.get('entries', 0) <= per, f"{d1}")
    e.send('setoption name Clear Hash')
    d2 = info()
    check("Clear Hash → 항목 0, 용량 유지", d2.get('entries') == 0 and d2.get('capacity') == per, f"{d2}")
    e.send('go nodes 20000')
    e.bestmove(30)
    e.send('setoption name Hash value 2')
    d3 = info()
    check(f"Hash 2로 바꾸면 용량 {2 * per}의 빈 표 (내용 비움)",
          d3.get('capacity') == 2 * per and d3.get('entries') == 0 and d3.get('hash_mb') == 2, f"{d3}")
    e.send('go nodes 20000')
    e.bestmove(30)
    e.send('ucinewgame')
    d4 = info()
    check("ucinewgame → TT 비움", d4.get('entries') == 0, f"{d4}")
    e.send('setoption name Hash value 0')
    e.send('setoption name Hash value 99999')
    d5 = info()
    check("범위 밖 값은 1~1024로 잘라서 적용", d5.get('hash_mb') == 1024 and d5.get('capacity') == 1024 * per,
          f"{d5.get('hash_mb')}")
    e.send('isready')
    line, _, _ = e.wait_for(lambda l: l == 'readyok', 10)
    check("큰 표(1024MB 설정)를 만든 뒤에도 응답", line == 'readyok')
    e.close()


def test_v041_kingsafety_option():
    section("v0.4.1  KingSafety 옵션 (평가의 킹 안전 항목 켬/끔, 비교 실험용)")
    import evaluate
    from search import Searcher
    fen = "r1b3rk/pppp3p/2n2n2/2b1p3/2B1P2q/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"   # 룩·퀸이 백 킹을 노림
    e = Engine()
    e.send('uci')
    _, got, _ = e.wait_for(lambda l: l == 'uciok', 5)
    advertised = f'option name KingSafety type check default {str(evaluate.KING_SAFETY).lower()}' in got

    def score():
        e.send(f'position fen {fen}')
        e.send('go depth 2')
        _, lines, _ = e.bestmove(30)
        last = [l for l in lines if l.startswith('info depth 2 ')][-1]
        return int(last.split(' score cp ')[1].split()[0])
    e.send('setoption name KingSafety value true')      # 기본값이 무엇이든 켠 상태에서 시작
    on1 = score()
    e.send('setoption name KingSafety value false')
    off = score()
    e.send('setoption name KingSafety value true')
    on2 = score()
    e.close()
    ref = {}
    saved = evaluate.KING_SAFETY
    for flag in (True, False):
        evaluate.KING_SAFETY = flag
        ref[flag] = Searcher().search(Board(fen), max_depth=2, on_info=None)[1]
    evaluate.KING_SAFETY = saved
    check("옵션 광고(기본값 = evaluate.KING_SAFETY) / 끄면 점수가 바뀌고 다시 켜면 돌아옴 / 각각 직접 탐색한 점수와 같음",
          advertised and on1 == on2 == ref[True] and off == ref[False] and on1 != off,
          f"켬 {on1}, 끔 {off}, 다시 켬 {on2} (직접 {ref[True]}/{ref[False]})")


def test_python_chess_games():
    section("python-chess UCI 클라이언트로 실제 대국 (GUI 역할)")
    try:
        import chess
        import chess.engine
    except ImportError:
        skip("python-chess 대국", "python-chess 미설치 — pip install chess")
        return
    with chess.engine.SimpleEngine.popen_uci(ENGINE_CMD, cwd=HERE) as eng:
        check("python-chess가 엔진을 인식", eng.id.get('name', '').startswith('MyEngine'), eng.id.get('name'))
        info = eng.analyse(chess.Board(), chess.engine.Limit(depth=4))
        check("analyse: 점수·수순·깊이를 읽어 감", info.get('depth') == 4 and 'pv' in info and 'score' in info,
              f"{info.get('score')}, pv {' '.join(m.uci() for m in info['pv'])}")

    # 시간제 대국 (5초 + 0.1초): 시간패·불법수 없이 끝까지
    results, flags, max_think = [], 0, 0.0
    w = chess.engine.SimpleEngine.popen_uci(ENGINE_CMD, cwd=HERE)
    k = chess.engine.SimpleEngine.popen_uci(ENGINE_CMD, cwd=HERE)
    try:
        for g, opening in enumerate((['e2e4', 'c7c5'], ['d2d4', 'g8f6'])):
            board = chess.Board()
            for u in opening:
                board.push_uci(u)
            clock = {chess.WHITE: 5.0, chess.BLACK: 5.0}
            while not board.is_game_over(claim_draw=True) and board.ply() < 160:
                eng = w if board.turn == chess.WHITE else k
                limit = chess.engine.Limit(white_clock=clock[chess.WHITE], black_clock=clock[chess.BLACK],
                                           white_inc=0.1, black_inc=0.1)
                t0 = time.time()
                r = eng.play(board, limit)                   # 불법수면 python-chess가 예외를 냄
                used = time.time() - t0
                max_think = max(max_think, used)
                clock[board.turn] -= used
                if clock[board.turn] < 0:
                    flags += 1
                    break
                clock[board.turn] += 0.1
                board.push(r.move)
            results.append(board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else '*(160수)')
    finally:
        w.quit()
        k.quit()
    check("5초+0.1초 대국 2판: 불법수·시간패 없이 진행", flags == 0, f"결과 {results}, 한 수 최대 {max_think:.2f}s")

    # ponder 켠 대국: python-chess가 예상수 적중이면 ponderhit, 빗나가면 stop을 보냄
    w = chess.engine.SimpleEngine.popen_uci(ENGINE_CMD, cwd=HERE)
    k = chess.engine.SimpleEngine.popen_uci(ENGINE_CMD, cwd=HERE)
    flags, plies, hits = 0, 0, 0
    try:
        board = chess.Board()
        clock = {chess.WHITE: 5.0, chess.BLACK: 5.0}
        expected = {chess.WHITE: None, chess.BLACK: None}
        while not board.is_game_over(claim_draw=True) and board.ply() < 120:
            eng = w if board.turn == chess.WHITE else k
            limit = chess.engine.Limit(white_clock=clock[chess.WHITE], black_clock=clock[chess.BLACK],
                                       white_inc=0.1, black_inc=0.1)
            if board.move_stack and expected[board.turn] == board.move_stack[-1]:
                hits += 1
            t0 = time.time()
            r = eng.play(board, limit, ponder=True)
            used = time.time() - t0
            clock[board.turn] -= used
            if clock[board.turn] < 0:
                flags += 1
                break
            clock[board.turn] += 0.1
            expected[board.turn] = r.ponder
            board.push(r.move)
        plies = board.ply()
    finally:
        w.quit()
        k.quit()
    check("ponder 켠 5초+0.1초 대국: 불법수·시간패 없이 진행", flags == 0 and plies > 20,
          f"{plies}수(ply), 예상수 적중 {hits}번")


STUB_ENGINE = r"""
# match.py 오류 처리 시험용 '가짜 상대'. 체스 엔진이 아님: 탐색·평가 없이 python-chess가 주는 첫 합법수를 냄.
# 모드: ok / illegal(2번째 go에 불법수) / none(2번째 go에 0000) / crash(3번째 go에 종료) / slow(2번째 go에 1.5초 지연)
import sys, time, chess
mode = sys.argv[1]
board, gos = chess.Board(), 0
for line in sys.stdin:
    t = line.split()
    if not t:
        continue
    if t[0] == 'uci':
        print('id name Stub-' + mode)
        print('option name Hash type spin default 1 min 1 max 16')
        print('uciok')
    elif t[0] == 'isready':
        print('readyok')
    elif t[0] == 'position':
        k = t.index('moves') if 'moves' in t else len(t)
        board = chess.Board() if t[1] == 'startpos' else chess.Board(' '.join(t[2:k]))
        for u in t[k + 1:]:
            board.push_uci(u)
    elif t[0] == 'go':
        gos += 1
        mv = next(iter(board.legal_moves)).uci()
        if mode == 'illegal' and gos == 2:
            mv = 'a1h8' if not board.is_legal(chess.Move.from_uci('a1h8')) else 'h1a8'
        if mode == 'none' and gos == 2:
            mv = '0000'
        if mode == 'crash' and gos == 3:
            sys.exit(3)
        if mode == 'slow' and gos == 2:
            time.sleep(1.5)
        print('bestmove ' + mv)
    elif t[0] == 'quit':
        break
    sys.stdout.flush()
"""


def run_match(tmp, label, stub_mode, games, extra=()):
    stub = os.path.join(tmp, 'stub_engine.py')
    if not os.path.exists(stub):
        with open(stub, 'w') as f:
            f.write(STUB_ENGINE)
    pgn = os.path.join(tmp, label + '.pgn')
    cmd = [sys.executable, os.path.join(HERE, 'match.py'),
           '--engine1', f'{sys.executable} {os.path.join(HERE, "uci.py")}',
           '--engine2', f'{sys.executable} {stub} {stub_mode}',
           '--games', str(games), '--tc', '1+0.05', '--label', label, '--pgn', pgn, *extra]
    return cmd, pgn


def read_pgn_games(path):
    import chess.pgn
    out = []
    with open(path, encoding='utf-8') as f:
        while True:
            g = chess.pgn.read_game(f)
            if g is None:
                return out
            out.append(g)


def test_match_tool():
    section("match.py: 기록·집계·오류 처리·Elo 표시 (v0.4.1)")
    try:
        import chess
        import chess.pgn
    except ImportError:
        skip("match.py", "python-chess 미설치 — pip install chess")
        return
    import json
    import random
    import signal
    import tempfile
    sys.path.insert(0, HERE)
    import match as M
    tmp = tempfile.mkdtemp(prefix='match_test_')

    # ① Elo 계산: 0%·100%·전부 무승부에서 잘못된 수치를 내지 않음
    r0, r1, rd, rm = (M.elo_report(0, 0, 10, []), M.elo_report(10, 0, 0, []), M.elo_report(0, 10, 0, []),
                      M.elo_report(3, 4, 3, [0.5] * 5))
    check("점수율 0%·100%: Elo 값 없음(None) + 한쪽 95% 경계만, 전부 무승부: 범위 계산 불가 표시",
          r0['elo'] is None and r0['bound']['side'] == 'upper' and r0['bound']['elo'] < 0
          and r1['elo'] is None and r1['bound']['side'] == 'lower' and r1['bound']['elo'] > 0
          and rd['elo'] == 0 and rd['trinomial'].get('degenerate') and rm['elo'] == 0
          and rm['trinomial']['lo'] < 0 < rm['trinomial']['hi'] and rm['pairs']['degenerate'],
          f"0%: <={r0['bound']['elo']:.0f}, 100%: >={r1['bound']['elo']:.0f}, 3-4-3: +-{rm['trinomial']['hi']:.0f}")

    # ② 오류 처리: 불법수·수 없음·시간패·충돌 → 그 엔진의 패 + 기록 + 재시작 후 계속
    expect = {'illegal': 'illegal_move', 'none': 'no_move', 'slow': 'time_forfeit', 'crash': 'engine_crash'}
    for mode, term in expect.items():
        cmd, pgn = run_match(tmp, mode, mode, 2)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=tmp)
        try:
            d = json.load(open(pgn[:-4] + '.json', encoding='utf-8'))
            games, s = d['games'], d['summary']
            pg = read_pgn_games(pgn)
            rows = open(pgn[:-4] + '.csv', encoding='utf-8').read().strip().splitlines()
            key = {'illegal_move': 'illegal_moves', 'no_move': 'illegal_moves', 'time_forfeit': 'time_losses',
                   'engine_crash': 'engine_errors'}[term]
            ok = (p.returncode == 0 and d['completed'] and len(games) == 2 and len(pg) == 2 and len(rows) == 3
                  and all(g['termination'] == term and g['culprit'] == 2 and g['score1'] == 1 for g in games)
                  and s[key]['engine2'] == 2 and s[key]['engine1'] == 0 and d['restarts']['engine2'] == 2
                  and all(g.headers['Termination'] == M.PGN_TERMINATION[term] for g in pg))
            detail = f"{[g['termination'] for g in games]}, 재시작 {d['restarts']}"
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e} / {p.stdout[-300:]} {p.stderr[-300:]}"
        check(f"상대가 {mode}: 2판 모두 '{term}'로 상대 패, 집계·PGN Termination·CSV 일치, 재시작 뒤 다음 판 진행",
              ok, detail)

    # ③ 정상 대국: PGN 헤더에 실험 조건, 오프닝 쌍, 시드 재현, JSON 집계
    cmd, pgn = run_match(tmp, 'ok', 'ok', 4, ('--seed', '7'))
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=tmp)
    try:
        d = json.load(open(pgn[:-4] + '.json', encoding='utf-8'))
        pg = read_pgn_games(pgn)
        h = pg[0].headers
        need = ('White', 'Black', 'Result', 'TimeControl', 'Termination', 'TerminationDetail', 'Opening',
                'GameDuration', 'WhiteAvgThink', 'BlackMaxThink', 'WhiteOptions', 'BlackHash',
                'WhiteLimitStrength', 'BlackUCIElo', 'PythonVersion', 'OS', 'Seed')
        g = d['games']
        same_open = g[0]['opening'] == g[1]['opening'] and g[0]['engine1_color'] != g[1]['engine1_color']
        order = [o[0] for o in M.OPENINGS]
        random.Random(7).shuffle(order)
        legal = True
        for rec, x in zip(g, pg):                   # 수순을 처음부터 다시 둬서 합법인지, PGN과 같은지
            b = chess.Board()
            for u in rec['moves']:
                legal &= chess.Move.from_uci(u) in b.legal_moves
                b.push_uci(u)
            legal &= not x.errors and [m.uci() for m in x.mainline_moves()] == rec['moves']
        ok = (p.returncode == 0 and all(k in h for k in need) and h['TimeControl'] == '1+0.05' and same_open
              and d['conditions']['openings_used'] == order and g[0]['opening'] == order[0] and legal
              and d['summary']['total']['n'] == 4)
        detail = f"헤더 {len(h)}개, 오프닝 {g[0]['opening']}/{g[2]['opening']}, 결과 {[x['result'] for x in g]}"
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e} / {p.stdout[-300:]}"
    check("정상 4판: 조건 헤더 기록, 같은 오프닝을 색 바꿔 2판, 시드 순서 재현, 수순이 합법이고 PGN과 JSON 일치",
          ok, detail)

    # ④ 중간에 멈춰도(Ctrl+C) 끝난 판은 PGN·JSON·CSV에 남음
    cmd, pgn = run_match(tmp, 'intr', 'ok', 20)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=tmp)
    jpath = pgn[:-4] + '.json'
    t0 = time.time()
    while time.time() - t0 < 120:
        try:
            if len(json.load(open(jpath, encoding='utf-8'))['games']) >= 1:
                break
        except Exception:
            pass
        time.sleep(0.2)
    p.send_signal(signal.SIGINT)
    try:
        p.wait(timeout=30)
    except subprocess.TimeoutExpired:
        p.kill()
    try:
        d = json.load(open(jpath, encoding='utf-8'))
        pg = read_pgn_games(pgn)
        ok = (not d['completed'] and d['interrupted'] and 1 <= len(d['games']) < 20 and len(pg) == len(d['games'])
              and d['summary']['total']['n'] == len(d['games']))
        detail = f"{len(d['games'])}판 저장, {d['interrupted']}"
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    check("20판 중 Ctrl+C: 끝난 판까지 PGN·JSON 저장, completed=false", ok, detail)

    # ⑤ 실험 비교: 조건이 다르면 알림
    p = subprocess.run([sys.executable, os.path.join(HERE, 'match.py'), '--compare',
                        os.path.join(tmp, 'ok.json'), os.path.join(tmp, 'crash.json')],
                       capture_output=True, text=True, timeout=30)
    out = p.stdout
    check("--compare: 두 실험을 표로, 상대가 다르면 '다름' 표시",
          p.returncode == 0 and '\nok ' in out and '\ncrash ' in out and '다름' in out and '상대 엔진' in out,
          out.strip().splitlines()[-4] if out.strip() else p.stderr[-200:])


def test_match_v042():
    section("match.py v0.4.2: 변형 교차 실행·짝 비교·환경 기록·동시 실행 방지")
    try:
        import chess
    except ImportError:
        skip("match.py v0.4.2", "python-chess 미설치 — pip install chess")
        return
    import json
    import tempfile
    sys.path.insert(0, HERE)
    import match as M
    tmp = tempfile.mkdtemp(prefix='match_test2_')
    cmd, pgn = run_match(tmp, 'ab', 'ok', 4, ('--variant', 'off:KingSafety=false', '--variant', 'on:KingSafety=true'))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=tmp)
    # 실행 중에 두 번째 실험을 시작하면 거부되어야 함
    t0 = time.time()
    while time.time() - t0 < 30 and M.running_match() is None:
        time.sleep(0.05)
    cmd2, _ = run_match(tmp, 'second', 'ok', 2)
    p2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=60, cwd=tmp)
    out, _ = p.communicate(timeout=600)
    check("다른 실험이 실행 중이면 두 번째 match.py는 시작하지 않고 끝남 (대국 0판), 끝난 뒤에는 잠금이 풀림",
          p2.returncode != 0 and not os.path.exists(os.path.join(tmp, 'second.json')) and M.running_match() is None,
          (p2.stderr or p2.stdout).strip().splitlines()[0][:60] if (p2.stderr or p2.stdout).strip() else '')
    try:
        d = json.load(open(pgn[:-4] + '.json', encoding='utf-8'))
        g = d['games']
        order = [(x['variant'], x['engine1_color'], x['opening']) for x in g]
        o1, o2 = g[0]['opening'], g[4]['opening']
        want = [('off', 'white', o1), ('on', 'white', o1), ('on', 'black', o1), ('off', 'black', o1),
                ('on', 'white', o2), ('off', 'white', o2), ('off', 'black', o2), ('on', 'black', o2)]
        pg = read_pgn_games(pgn)
        ids_ok = all(x.headers['GameID'] == r['game_id'] and x.headers['ExperimentID'] == d['experiment_id']
                     and x.headers['Engine1Variant'] == r['variant'] for x, r in zip(pg, g))
        s = d['summary']
        pr = s['paired']
        diffs = [b['score1'] - a['score1'] for a in g if a['variant'] == 'off'
                 for b in g if b['variant'] == 'on' and b['game_index'] == a['game_index']]
        times_ok = all(M.parse_time(g[i]['finished']) <= M.parse_time(g[i + 1]['started']) for i in range(len(g) - 1))
        th = s['variants']['on']['think']['engine1']
        ok = (p.returncode == 0 and d['completed'] and order == want and len(pg) == 8 and ids_ok
              and set(s['variants']) == {'off', 'on'} and all(v['total']['n'] == 4 for v in s['variants'].values())
              and pr['pairs'] == 4 and abs(pr['mean_diff'] - sum(diffs) / 4) < 1e-9
              and pr['b_better'] + pr['same'] + pr['a_better'] == 4 and times_ok
              and th['avg_depth'] is not None and th['nps'] and s['variants']['on']['avg_plies']
              and d['conditions']['cpu_count'] == os.cpu_count() and d['conditions']['concurrent_with'] is None
              and all('started' in x and 'finished' in x for x in g))
        detail = f"순서 {[v[0][:2] + v[1][0] for v in order]}, 짝 차이 {pr['mean_diff']:+.2f}, 깊이 {th['avg_depth']}, NPS {th['nps']}"
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e} / {out[-300:]}"
    check("변형 2개 × 4판: A B B A / B A A B 순서로 순차 실행, 같은 오프닝·색끼리 짝 비교, PGN·JSON이 같은 "
          "ExperimentID·GameID, 시작·종료 시각이 겹치지 않음, 탐색 깊이·NPS·CPU 수 기록", ok, detail)
    ps = M.paired_stats([{'game_index': i, 'score1': a, 'engine1_color': 'white'} for i, a in enumerate([1, 0, 0.5, 0, 1, 0])],
                        [{'game_index': i, 'score1': b, 'engine1_color': 'white'} for i, b in enumerate([1, 1, 0.5, 1, 0, 1])])
    check("짝 통계 계산: 차이 [0,+1,0,+1,-1,+1] → 평균 +1/3, B 3 / 같음 2 / A 1, 부호 검정 p = 0.625",
          abs(ps['mean_diff'] - 1 / 3) < 1e-9 and (ps['b_better'], ps['same'], ps['a_better']) == (3, 2, 1)
          and abs(ps['sign_test_p'] - 0.625) < 1e-9 and ps['lo'] < 0 < ps['hi'], f"{ps['mean_diff']:.3f} p={ps['sign_test_p']}")
    pc = subprocess.run([sys.executable, os.path.join(HERE, 'match.py'), '--compare', pgn[:-4] + '.json'],
                        capture_output=True, text=True, timeout=30)
    check("--compare: 변형마다 한 줄 + 짝 비교 + 실행 환경 출력",
          pc.returncode == 0 and 'ab/off' in pc.stdout and 'ab/on' in pc.stdout and '짝 비교' in pc.stdout
          and '실행 환경' in pc.stdout, pc.stderr[-200:])



def test_v043_tactical_checks():
    section("v0.4.3  TacticalChecks 실험 옵션 및 탐색 결과 차이")
    e = Engine()
    try:
        e.send('uci')
        _, got, _ = e.wait_for(lambda x: x == 'uciok', 5)
        check("TacticalChecks 옵션 광고 (기본 비활성)",
              'option name TacticalChecks type check default false' in got)
        trap = '7k/8/6K1/8/8/8/6b1/R4Q2 b - - 0 1'
        e.send('position fen ' + trap)
        # TacticalChecks is tested with the selective profile disabled.
        e.send('setoption name SelectiveSearch value false')
        e.send('setoption name TacticalChecks value false')
        e.send('go depth 1')
        off, _, _ = e.bestmove(5)
        e.send('setoption name TacticalChecks value true')
        e.send('go depth 1')
        on, _, _ = e.bestmove(5)
        check("TacticalChecks OFF는 퀸 미끼 Bxf1 선택, ON은 Ra8#을 보고 회피",
              off == 'g2f1' and on != 'g2f1' and legal_after(trap, [], on),
              f'off={off}, on={on}')
        e.send('setoption name SelectiveSearch value true')
        e.send('setoption name TacticalChecks value false')
        e.send('go depth 1')
        selective, _, _ = e.bestmove(5)
        check("SelectiveSearch를 켜면 TacticalChecks가 꺼져 있어도 깊이 1에서 미끼를 피함",
              selective != 'g2f1' and legal_after(trap, [], selective), f'selective={selective}')
        e.send('isready')
        line, _, _ = e.wait_for(lambda x: x == 'readyok', 2)
        check("TacticalChecks 변경 후에도 GUI 명령 정상", line == 'readyok')
    finally:
        e.close()

if __name__ == '__main__':
    t0 = time.time()
    for t in (test_handshake_and_basic, test_time_controls, test_stop_infinite, test_terminal_and_history,
              test_robustness, test_v041_searchmoves_nodes, test_v041_stop_races, test_v041_ponder,
              test_v041_hash, test_v041_kingsafety_option, test_v043_tactical_checks,
              test_python_chess_games, test_match_tool, test_match_v042):
        t()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n총 {len(RESULTS)}개 중 {len(RESULTS) - len(failed)}개 통과  ({time.time() - t0:.0f}s)")
    if SKIPPED:
        print(f"건너뜀 {len(SKIPPED)}개 (통과로 세지 않음):", *SKIPPED, sep='\n  ')
    if failed:
        print("실패:", *failed, sep='\n  ')
        raise SystemExit(1)
