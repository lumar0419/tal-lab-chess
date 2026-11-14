"""
match.py — 엔진끼리 자동 대국 + 실험 비교 + 패배 원인 분석 (개발용 도구, python-chess 필요: pip install chess)

예)
  # 내 엔진 vs Stockfish(설정 Elo 1700), 20판, 10초+0.1초
  python match.py --engine1 "python uci.py" --engine2 "stockfish" \\
                  --opt2 UCI_LimitStrength=true --opt2 UCI_Elo=1700 --games 20 --tc 10+0.1 --label base --pgn base.pgn

  # 설정 비교 실험 (v0.4.2): 같은 엔진의 옵션만 바꾼 '변형'들을 한 번의 실행 안에서 번갈아 순차 대국
  python match.py --engine1 "python uci.py" --engine2 "stockfish" \\
                  --opt2 UCI_LimitStrength=true --opt2 UCI_Elo=1700 --games 40 --tc 10+0.1 \\
                  --variant ks_off:KingSafety=false --variant ks_on:KingSafety=true --label ks --pgn ks.pgn

  # 결과 비교 (조건이 같은지, 실행 시간이 겹쳤는지도 알려 줌)
  python match.py --compare a.json b.json

  # 진 대국 분석 (Stockfish를 분석 엔진으로): 결정적 실수, 더 나은 수, 추정 원인
  python match.py --analyze ks.json --analyzer stockfish

방식
  · 오프닝 10개를 차례로(또는 --seed로 섞은 순서로) 쓰고, 같은 오프닝을 색을 바꿔 두 번씩 둠
  · 변형이 있으면 오프닝마다 A B B A / B A A B 순서로 번갈아 둠 → 실험 순서가 한 설정에 유리하지 않게.
    변형별 --games 판씩 (총 판 수 = games × 변형 수). 같은 오프닝·같은 색끼리 짝지어 차이를 냄
  · 한 컴퓨터에서 실험은 한 번에 하나만: 다른 match.py가 돌고 있으면 시작하지 않음 (잠금 파일).
    --allow-concurrent로 강제할 수 있고, 그 사실이 결과에 기록됨
  · 시계를 직접 재서 시간을 넘기면 시간패, 불법수·응답 없음·엔진 종료는 그 엔진의 패
    문제를 일으킨 엔진은 같은 설정으로 다시 띄워 다음 판을 계속함
  · 3회 반복·50수 규칙은 GUI처럼 바로 무승부로 판정, 400 ply가 넘으면 무승부(판정)
  · 한 판이 끝날 때마다 PGN·JSON·CSV를 저장 → 중간에 멈추거나 오류가 나도 끝난 판은 남음

기록
  PGN 헤더   표준 태그 + 확장 태그(실험 ID·판 ID, 변형, 엔진 옵션·Hash·강도 설정, 오프닝, 종료 사유 상세,
             시작·종료 시각, 생각 시간, 탐색 깊이·노드·NPS, 시스템 부하, Python·OS·CPU 수)
  JSON       실험 조건 + 판별 기록(수순 포함) + 집계. PGN과 같은 ExperimentID / GameID로 이어짐
  CSV        판별 한 줄씩 (스프레드시트용)
  실행 환경  판마다 시작·종료 시각, 시스템 부하(1분 평균), 그 판 동안 일한 CPU 코어 수(Linux)
             → 순차 대국이면 '일한 코어'가 1 안팎. 1.5를 넘는 판이 많으면 다른 부하가 있었던 것
"""

import argparse
import csv
import datetime
import json
import math
import os
import platform
import random
import shlex
import sys
import tempfile
import time

try:
    import chess
    import chess.engine
    import chess.pgn
except ImportError:
    sys.exit("match.py는 python-chess가 필요해요: pip install chess  (엔진 자체는 필요 없음)")

MATCH_VERSION = "0.4.2"
OPENINGS = [
    ("Open Game", "e2e4 e7e5 g1f3 b8c6"),
    ("Sicilian", "e2e4 c7c5 g1f3 d7d6"),
    ("Queen's Gambit Declined", "d2d4 d7d5 c2c4 e7e6"),
    ("King's Indian", "d2d4 g8f6 c2c4 g7g6"),
    ("French", "e2e4 e7e6 d2d4 d7d5"),
    ("Caro-Kann", "e2e4 c7c6 d2d4 d7d5"),
    ("English", "c2c4 e7e5 b1c3 g8f6"),
    ("Reti", "g1f3 d7d5 g2g3 g8f6"),
    ("Nimzo/Queen's Indian", "d2d4 g8f6 c2c4 e7e6"),
    ("Scandinavian", "e2e4 d7d5 e4d5 d8d5"),
]
MAX_PLIES = 400
STRENGTH_OPTS = ('uci_limitstrength', 'uci_elo', 'skill level')

# 종료 사유 → PGN 표준 Termination 값
PGN_TERMINATION = {
    'checkmate': 'normal', 'stalemate': 'normal', 'insufficient_material': 'normal',
    'seventyfive_moves': 'normal', 'fivefold_repetition': 'normal',
    'threefold_repetition': 'normal', 'fifty_moves': 'normal',
    'max_plies': 'adjudication',
    'time_forfeit': 'time forfeit', 'engine_unresponsive': 'time forfeit',
    'illegal_move': 'rules infraction', 'no_move': 'rules infraction',
    'engine_crash': 'abandoned', 'engine_error': 'abandoned',
}
FAULTS = ('time_forfeit', 'engine_unresponsive', 'illegal_move', 'no_move', 'engine_crash', 'engine_error')


# ──────────────────────────────── 엔진 ────────────────────────────────
def parse_opts(items):
    opts = {}
    for item in items or []:
        name, _, value = item.partition('=')
        v = value.strip()
        opts[name.strip()] = {'true': True, 'false': False}.get(v.lower(), int(v) if v.lstrip('-').isdigit() else v)
    return opts


def fmt_opts(opts):
    return '; '.join(f"{k}={str(v).lower() if isinstance(v, bool) else v}" for k, v in opts.items()) or '(default)'


class Player:
    """엔진 프로세스 하나와 그 설정. 충돌·응답 없음 뒤에는 같은 설정으로 다시 띄움."""

    def __init__(self, cmd, opts, fallback_name):
        self.cmd, self.opts = cmd, dict(opts)
        self.restarts = 0
        self.eng = None
        self.start()
        self.name = self.eng.id.get('name', fallback_name)
        self.author = self.eng.id.get('author', '')

    def start(self):
        eng = chess.engine.SimpleEngine.popen_uci(shlex.split(self.cmd), timeout=30)
        try:
            if self.opts:
                eng.configure(self.opts)        # 없는 옵션·범위 밖 값이면 여기서 오류 (조용히 무시하지 않음)
        except Exception:
            try:
                eng.quit()
            except Exception:
                eng.close()
            raise
        self.eng = eng
        self.declared = dict(eng.options)       # 엔진이 알린 옵션 (엔진이 죽은 뒤에도 기록에 쓸 수 있게 복사)

    def close(self):
        if self.eng is None:
            return
        try:
            self.eng.quit()
        except Exception:
            try:
                self.eng.close()
            except Exception:
                pass
        self.eng = None

    def restart(self):
        self.close()
        self.restarts += 1
        self.start()

    def option(self, name):
        """설정한 값, 없으면 엔진이 알린 기본값, 그 옵션이 없으면 None"""
        for k, v in self.opts.items():
            if k.lower() == name.lower():
                return v
        for k, opt in self.declared.items():
            if k.lower() == name.lower():
                return opt.default
        return None

    def describe(self):
        return {"name": self.name, "author": self.author, "cmd": self.cmd, "options": self.opts,
                "hash_mb": self.option('Hash'), "threads": self.option('Threads'),
                "uci_limitstrength": self.option('UCI_LimitStrength'), "uci_elo": self.option('UCI_Elo'),
                "skill_level": self.option('Skill Level')}


def opening_board(opening):
    b = chess.Board()
    for u in opening[1].split():
        b.push_uci(u)
    return b


def strength_check(player, openings, depth=8):
    """강도 제한 옵션(UCI_LimitStrength·UCI_Elo·Skill Level)을 설정했다면 실제로 적용됐는지 확인.
    ① 옵션이 엔진에 있는지·짝이 맞는지 ② 같은 국면을 같은 깊이로, 제한 설정과 제한을 뺀 설정으로
    두게 해서 고른 수가 달라지는지 (하나도 안 다르면 제한이 실제로는 꺼져 있을 가능성이 큼).
    설정 Elo는 그 엔진이 정한 척도의 '목표값'일 뿐, 이 대국 조건에서의 실제 실력이 아님."""
    low = {k.lower(): v for k, v in player.opts.items()}
    if not any(k in low for k in STRENGTH_OPTS):
        return {"requested": False}
    rep = {"requested": True, "notes": []}
    if 'uci_elo' in low:
        opt = player.eng.options.get('UCI_Elo')
        rep["uci_elo"] = low['uci_elo']
        if opt is not None:
            rep["uci_elo_range"] = [opt.min, opt.max]
        if low.get('uci_limitstrength') is not True:
            rep["notes"].append("UCI_Elo만 있고 UCI_LimitStrength=true가 없음 → 대부분의 엔진은 UCI_Elo를 무시")
    free_opts = {k: v for k, v in player.opts.items() if k.lower() not in STRENGTH_OPTS}
    free = None
    try:
        free = chess.engine.SimpleEngine.popen_uci(shlex.split(player.cmd), timeout=30)
        if free_opts:
            free.configure(free_opts)
        differ = 0
        for op in openings:
            b = opening_board(op)
            a = player.eng.play(b, chess.engine.Limit(depth=depth), game=object()).move
            c = free.play(b, chess.engine.Limit(depth=depth), game=object()).move
            differ += a != c
        rep["probe"] = {"positions": len(openings), "depth": depth, "different_moves": differ}
        if differ == 0:
            rep["notes"].append(f"오프닝 국면 {len(openings)}개에서 제한 없는 설정과 고른 수가 모두 같음 "
                                "→ 강도 제한이 적용되지 않았을 가능성")
    except Exception as e:                      # 확인 실패는 대국을 막지 않음 (기록만)
        rep["notes"].append(f"강도 확인 실패: {type(e).__name__}: {e}")
    finally:
        if free is not None:
            try:
                free.quit()
            except Exception:
                pass
    rep["applied"] = bool(rep.get("probe", {}).get("different_moves")) and not rep["notes"]
    return rep


# ──────────────────────────────── 실험 환경 · 한 판 ────────────────────────────────
LOCK_PATH = os.path.join(tempfile.gettempdir(), 'chess_engine_match.lock')


def _pid_alive(pid):
    """POSIX에서만 확인 가능. (Windows의 os.kill은 프로세스를 끝내 버리므로 쓰지 않음 → None)"""
    if os.name != 'posix':
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError, TypeError):
        return False


def running_match():
    """이 컴퓨터에서 지금 돌고 있는 다른 match.py 실험 (없으면 None).
    잠금 파일에 적힌 프로세스가 살아 있는지로 판단. 확인할 수 없는 운영체제에서는
    잠금 파일이 최근 30분 안에 갱신됐는지로 판단 (실험은 한 판이 끝날 때마다 갱신함)."""
    try:
        with open(LOCK_PATH, encoding='utf-8') as f:
            other = json.load(f)
        alive = _pid_alive(other.get('pid'))
        if alive is None:
            alive = time.time() - os.path.getmtime(LOCK_PATH) < 1800
        return other if alive and other.get('pid') != os.getpid() else None
    except (OSError, ValueError):
        return None


def write_lock(info):
    try:
        with open(LOCK_PATH, 'w', encoding='utf-8') as f:
            json.dump(info, f)
        return True
    except OSError:
        return False


def release_lock():
    try:
        with open(LOCK_PATH, encoding='utf-8') as f:
            if json.load(f).get('pid') == os.getpid():
                os.remove(LOCK_PATH)
    except (OSError, ValueError):
        pass


def load1():
    """1분 평균 시스템 부하 (실행 대기 중인 프로세스 수). 지원하지 않는 운영체제(Windows)는 None"""
    try:
        return round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        return None


def cpu_times():
    """(전체 시간, 쉬는 시간) — Linux /proc/stat. 다른 운영체제는 None"""
    try:
        with open('/proc/stat') as f:
            v = [int(x) for x in f.readline().split()[1:9]]
        return sum(v), v[3] + v[4]
    except (OSError, ValueError, IndexError):
        return None


def busy_cores(a, b):
    """두 시점 사이에 평균적으로 일하던 CPU 코어 수 (시스템 전체). 순차 대국 한 판이면 1 안팎이 정상."""
    if not a or not b or b[0] == a[0]:
        return None
    return round((1 - (b[1] - a[1]) / (b[0] - a[0])) * (os.cpu_count() or 1), 2)


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def parse_time(text):
    t = datetime.datetime.fromisoformat(text)
    return t if t.tzinfo else t.astimezone()


def play_game(players, opening, white_idx, args, round_no, meta=None):
    """한 판. players = [engine1(또는 그 변형), engine2]. meta = 실험 ID·변형 이름·변형 안에서의 판 번호"""
    meta = meta or {}
    variant = meta.get('variant')
    g_index = meta.get('game_index', round_no - 1)
    board = opening_board(opening)
    clock = {chess.WHITE: args.base, chess.BLACK: args.base}
    who = {chess.WHITE: white_idx, chess.BLACK: 1 - white_idx}
    think = {0: [], 1: []}
    depths = {0: [], 1: []}
    nodes = {0: 0, 1: 0}
    node_time = {0: 0.0, 1: 0.0}
    game_id = object()
    term = detail = culprit = None
    result = None
    started, load_a, cpu_a = now_iso(), load1(), cpu_times()
    t_start = time.monotonic()
    while True:
        outcome = board.outcome(claim_draw=True)
        if outcome:
            result = outcome.result()
            term = outcome.termination.name.lower()
            break
        if board.ply() >= MAX_PLIES:
            result, term, detail = '1/2-1/2', 'max_plies', f'{MAX_PLIES} plies'
            break
        idx = who[board.turn]
        p = players[idx]
        if args.movetime:
            limit = chess.engine.Limit(time=args.movetime / 1000)
        elif args.depth:
            limit = chess.engine.Limit(depth=args.depth)
        else:
            limit = chess.engine.Limit(white_clock=clock[chess.WHITE], black_clock=clock[chess.BLACK],
                                       white_inc=args.inc, black_inc=args.inc)
        t0 = time.monotonic()
        r = None
        try:
            r = p.eng.play(board, limit, game=game_id, info=chess.engine.INFO_ALL)
        except chess.engine.EngineTerminatedError as e:
            term, detail = 'engine_crash', f'{p.name}: {e}'
        except chess.engine.EngineError as e:      # python-chess는 불법·잘못된 bestmove를 EngineError로 알림
            msg = str(e)
            term = 'illegal_move' if ('illegal' in msg.lower() or 'invalid' in msg.lower()) else 'engine_error'
            detail = f'{p.name}: {msg[:120]}'
        except TimeoutError:                       # 남은 시간 + 10초가 지나도 bestmove가 없음
            term, detail = 'engine_unresponsive', f'{p.name}: no bestmove'
        used = time.monotonic() - t0
        think[idx].append(used)
        if r is not None:                          # 엔진이 알린 탐색 깊이·노드 수 (알리지 않는 엔진은 비어 있음)
            if isinstance(r.info.get('depth'), int):
                depths[idx].append(r.info['depth'])
            if isinstance(r.info.get('nodes'), int):
                nodes[idx] += r.info['nodes']
                node_time[idx] += used
        if term is None and not args.movetime and not args.depth:
            clock[board.turn] -= used
            if clock[board.turn] < 0:
                term, detail = 'time_forfeit', f'{p.name} lost on time ({-clock[board.turn]:.2f}s over)'
            else:
                clock[board.turn] += args.inc
        if term is None and (not r.move or r.move not in board.legal_moves):
            # python-chess는 'bestmove 0000'을 널 무브로 받아들여 그대로 두면 차례만 넘어감 (v0.4.0 match.py의 결함)
            term = 'no_move' if not r.move else 'illegal_move'
            detail = f"{p.name} returned {'no move' if not r.move else 'illegal ' + r.move.uci()}"
        if term is not None:
            culprit = idx
            result = '0-1' if board.turn == chess.WHITE else '1-0'
            break
        board.push(r.move)
    duration = time.monotonic() - t_start

    stats = {}
    for side, color in (('white', chess.WHITE), ('black', chess.BLACK)):
        i = who[color]
        ts, ds = think[i], depths[i]
        stats[side] = {"moves": len(ts), "avg": round(sum(ts) / len(ts), 3) if ts else 0.0,
                       "max": round(max(ts), 3) if ts else 0.0, "total": round(sum(ts), 3),
                       "depth_moves": len(ds), "depth_sum": sum(ds),
                       "avg_depth": round(sum(ds) / len(ds), 2) if ds else None,
                       "nodes": nodes[i], "node_time": round(node_time[i], 3),
                       "nps": int(nodes[i] / node_time[i]) if node_time[i] > 0 and nodes[i] else None}
    score1 = 0.5 if result == '1/2-1/2' else float((result == '1-0') == (white_idx == 0))
    names = [players[0].name + (f" [{variant}]" if variant else ''), players[1].name]
    exp = meta.get('experiment_id')
    rec = {"round": round_no, "experiment_id": exp,
           "game_id": f"{exp}-{round_no:03d}" if exp else str(round_no),
           "variant": variant, "game_index": g_index, "pair": g_index // 2 + 1, "opening": opening[0],
           "opening_moves": opening[1], "engine1_color": 'white' if white_idx == 0 else 'black',
           "white": names[white_idx], "black": names[1 - white_idx],
           "result": result, "score1": score1, "termination": term,
           "termination_detail": detail or term, "culprit": (None if culprit is None else culprit + 1),
           "plies": board.ply(), "moves": [m.uci() for m in board.move_stack],
           "started": started, "finished": now_iso(), "duration_s": round(duration, 2),
           "load_start": load_a, "load_end": load1(), "cpu_busy_cores": busy_cores(cpu_a, cpu_times()),
           "think": stats}
    return rec, board


def make_pgn(rec, board, players, white_idx, args, cond):
    game = chess.pgn.Game.from_board(board)
    wp, bp = players[white_idx], players[1 - white_idx]

    def side_tags(prefix, p, st):
        tags = {f"{prefix}Options": fmt_opts(p.opts), f"{prefix}Hash": str(p.option('Hash')),
                f"{prefix}LimitStrength": str(p.option('UCI_LimitStrength')).lower()
                if p.option('UCI_LimitStrength') is not None else '-',
                f"{prefix}UCIElo": str(p.option('UCI_Elo')) if p.option('UCI_Elo') is not None else '-',
                f"{prefix}AvgThink": f"{st['avg']:.3f}s", f"{prefix}MaxThink": f"{st['max']:.3f}s"}
        if st.get('avg_depth') is not None:
            tags[f"{prefix}AvgDepth"] = f"{st['avg_depth']:.2f}"
        if st.get('nps'):
            tags[f"{prefix}Nodes"] = str(st['nodes'])
            tags[f"{prefix}NPS"] = str(st['nps'])
        return tags

    start = parse_time(rec['started']).astimezone(datetime.timezone.utc)
    h = {"Event": args.label or "match.py", "Site": "?", "Date": parse_time(rec['started']).strftime("%Y.%m.%d"),
         "Round": str(rec['round']), "White": rec['white'], "Black": rec['black'], "Result": rec['result'],
         "TimeControl": cond['pgn_timecontrol'], "Termination": PGN_TERMINATION.get(rec['termination'], 'normal'),
         "PlyCount": str(rec['plies']), "UTCDate": start.strftime("%Y.%m.%d"), "UTCTime": start.strftime("%H:%M:%S"),
         "ExperimentID": str(rec.get('experiment_id')), "GameID": rec['game_id'],
         "TerminationDetail": rec['termination_detail'], "Opening": rec['opening'],
         "OpeningMoves": rec['opening_moves'], "Limit": cond['limit'],
         "StartTime": rec['started'], "EndTime": rec['finished'], "GameDuration": f"{rec['duration_s']:.1f}s",
         "PythonVersion": cond['python'], "OS": cond['os'], "CPUCount": str(cond.get('cpu_count')),
         "MatchTool": f"match.py {MATCH_VERSION}"}
    if rec.get('variant'):
        h["Engine1Variant"] = rec["variant"]      # "Variant"는 PGN에서 체스 변형(960 등)을 뜻하는 태그라 쓰지 않음
    if rec.get('load_start') is not None:
        h["SystemLoad"] = f"{rec['load_start']}"
    if rec.get('cpu_busy_cores') is not None:
        h["CPUBusyCores"] = f"{rec['cpu_busy_cores']}"
    h.update(side_tags("White", wp, rec['think']['white']))
    h.update(side_tags("Black", bp, rec['think']['black']))
    if cond.get('seed') is not None:
        h["Seed"] = str(cond['seed'])
    game.headers.update(h)
    return game


# ──────────────────────────────── 통계 ────────────────────────────────
def to_elo(p):
    """점수율 → Elo 차이 (로지스틱 모델). 0 이하·1 이상이면 None (무한대)"""
    if p <= 0 or p >= 1:
        return None
    return -400 * math.log10(1 / p - 1) + 0.0      # + 0.0: 점수율 50%에서 -0 대신 +0


def elo_report(w, d, l, pair_scores, z=1.96):
    """Elo 차이 추정.
    가정: 판(또는 오프닝 쌍)이 서로 독립이고, 평균 점수가 정규분포에 가깝다(중심극한정리).
          Elo 모델은 기대 점수 = 1 / (1 + 10^(-차이/400)).
    · 삼항(승·무·패) 오차: 판 하나하나를 독립으로 봄.
    · 쌍 오차: 같은 오프닝을 색을 바꿔 둔 두 판을 한 묶음으로 봄 → 오프닝 유불리로 생기는
      판 사이의 상관을 반영 (쌍이 충분하면 이쪽이 더 정직한 범위).
    · 점수율 0%·100%는 Elo가 무한대 → 값 대신 한쪽 95% 경계만 (무승부가 없을 때의 이항 분포 기준).
    표본이 작으면 정규 근사 자체가 부정확하므로 범위도 '대략'으로만 읽어야 함."""
    n = w + d + l
    if n == 0:
        return None
    s = (w + 0.5 * d) / n
    rep = {"games": n, "score": s, "elo": to_elo(s), "z": z}
    if w + l > 0:
        rep["los"] = 0.5 * (1 + math.erf((w - l) / math.sqrt(2 * (w + l))))   # 우세할 확률 (무승부 제외)
    if 0 < s < 1:
        var = (w * (1 - s) ** 2 + d * (0.5 - s) ** 2 + l * s ** 2) / n
        se = math.sqrt(var / n)
        if se > 0:
            rep["trinomial"] = {"se": se, "lo": to_elo(s - z * se), "hi": to_elo(s + z * se)}
        else:                                   # 모든 판이 무승부: 분산 0 → 범위 폭 0은 거짓 정밀도
            rep["trinomial"] = {"se": 0.0, "lo": None, "hi": None, "degenerate": True}
    elif s == 0:
        rep["bound"] = {"side": "upper", "elo": to_elo(1 - 0.05 ** (1 / n))}
    else:
        rep["bound"] = {"side": "lower", "elo": to_elo(0.05 ** (1 / n))}
    if len(pair_scores) >= 2:
        k = len(pair_scores)
        m = sum(pair_scores) / k
        var_p = sum((x - m) ** 2 for x in pair_scores) / k
        se_p = math.sqrt(var_p / k)
        ok = 0 < m < 1 and se_p > 0
        rep["pairs"] = {"pairs": k, "score": m, "se": se_p, "elo": to_elo(m),
                        "lo": to_elo(m - z * se_p) if ok else None,
                        "hi": to_elo(m + z * se_p) if ok else None, "degenerate": not ok}
    return rep


def wdl(rows):
    w = sum(r['score1'] == 1 for r in rows)
    d = sum(r['score1'] == 0.5 for r in rows)
    l = sum(r['score1'] == 0 for r in rows)
    n = w + d + l
    return {"w": w, "d": d, "l": l, "n": n, "score": (w + 0.5 * d) / n if n else None}


def engine_stats(records, i):
    """engine i(1 또는 2)의 수당 생각 시간·탐색 깊이·노드 집계"""
    n = tot = mx = dn = ds = nodes = nt = 0
    for r in records:
        side = r['think']['white' if (r['engine1_color'] == 'white') == (i == 1) else 'black']
        n += side['moves']
        tot += side['total']
        mx = max(mx, side['max'])
        dn += side.get('depth_moves', 0)
        ds += side.get('depth_sum', 0)
        nodes += side.get('nodes', 0)
        nt += side.get('node_time', 0)
    return {"moves": n, "avg": round(tot / n, 3) if n else 0.0, "max": round(mx, 3),
            "avg_depth": round(ds / dn, 2) if dn else None, "nodes": nodes,
            "avg_nodes": int(nodes / n) if n and nodes else None, "nps": int(nodes / nt) if nt > 0 and nodes else None}


def environment_stats(records):
    loads = [r['load_start'] for r in records if r.get('load_start') is not None]
    busy = [r['cpu_busy_cores'] for r in records if r.get('cpu_busy_cores') is not None]
    return {"load_mean": round(sum(loads) / len(loads), 2) if loads else None,
            "load_max": max(loads) if loads else None,
            "cpu_busy_cores_mean": round(sum(busy) / len(busy), 2) if busy else None,
            "cpu_busy_cores_max": max(busy) if busy else None,
            "games_busy_over_1_5": sum(b > 1.5 for b in busy)}


def paired_stats(recs_a, recs_b, z=1.96):
    """두 변형 A, B의 짝 비교. 짝 = 변형 안에서의 판 번호가 같은 두 판 (같은 오프닝, 같은 색).
    차이 d = B의 점수 − A의 점수 (−1, −0.5, 0, +0.5, +1).
    가정: 짝끼리 독립, 평균 차이가 정규분포에 가까움 (짝이 수십 개 이상일 때 근사).
    같은 오프닝이어도 실제 수순은 판마다 달라지므로(상대의 무작위성, 시간 차이) 짝짓기가 없애 주는 것은
    오프닝·색의 유불리뿐임. 부호 검정은 분포 가정 없이 'B가 더 나은 짝'과 'A가 더 나은 짝'의 수만 봄."""
    a = {r['game_index']: r for r in recs_a}
    b = {r['game_index']: r for r in recs_b}
    keys = sorted(set(a) & set(b))
    if not keys:
        return None
    d = [b[k]['score1'] - a[k]['score1'] for k in keys]
    n = len(d)
    mean = sum(d) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n > 1 else None
    plus, minus = sum(x > 0 for x in d), sum(x < 0 for x in d)
    m = plus + minus
    p_sign = min(1.0, 2 * sum(math.comb(m, i) for i in range(min(plus, minus) + 1)) / 2 ** m) if m else 1.0
    out = {"pairs": n, "mean_diff": mean, "se": se,
           "lo": mean - z * se if se else None, "hi": mean + z * se if se else None,
           "b_better": plus, "same": n - m, "a_better": minus, "sign_test_p": p_sign, "by_color": {}}
    for col in ('white', 'black'):
        dc = [b[k]['score1'] - a[k]['score1'] for k in keys if a[k]['engine1_color'] == col]
        if dc:
            out["by_color"][col] = {"pairs": len(dc), "mean_diff": sum(dc) / len(dc)}
    return out


def summarize(records, players_desc):
    s = {"total": wdl(records),
         "engine1_white": wdl([r for r in records if r['engine1_color'] == 'white']),
         "engine1_black": wdl([r for r in records if r['engine1_color'] == 'black']),
         "by_opening": {}}
    for r in records:
        s["by_opening"].setdefault(r['opening'], []).append(r)
    s["by_opening"] = {k: wdl(v) for k, v in s["by_opening"].items()}
    terms = {}
    for r in records:
        terms[r['termination']] = terms.get(r['termination'], 0) + 1
    s["terminations"] = terms
    s["mate_wins"] = sum(r['termination'] == 'checkmate' and r['score1'] == 1 for r in records)
    s["mate_losses"] = sum(r['termination'] == 'checkmate' and r['score1'] == 0 for r in records)
    for key, kinds in (("time_losses", ('time_forfeit', 'engine_unresponsive')),
                       ("illegal_moves", ('illegal_move', 'no_move')),
                       ("engine_errors", ('engine_crash', 'engine_error'))):
        s[key] = {f"engine{i}": sum(r['culprit'] == i and r['termination'] in kinds for r in records)
                  for i in (1, 2)}
    s["think"] = {f"engine{i}": engine_stats(records, i) for i in (1, 2)}
    s["avg_plies"] = round(sum(r['plies'] for r in records) / len(records), 1) if records else None
    s["environment"] = environment_stats(records)
    pairs = {}
    for r in records:
        pairs.setdefault(r['pair'], []).append(r['score1'])
    pair_scores = [sum(v) / 2 for v in pairs.values() if len(v) == 2]
    t = s["total"]
    s["elo"] = elo_report(t['w'], t['d'], t['l'], pair_scores)
    s["unpaired_games"] = sum(len(v) for v in pairs.values() if len(v) != 2)
    # 상대가 '설정 Elo'로 강도를 제한했으면 그 값을 기준으로 환산한 참고값
    opp = players_desc[1]
    st = opp.get('strength', {})
    if s["elo"] and opp.get('uci_limitstrength') is True and isinstance(opp.get('uci_elo'), int):
        e = s["elo"]
        anchor = opp['uci_elo']
        ref = {"anchor": anchor, "strength_applied": st.get('applied', False)}
        if e.get('elo') is not None:
            ref["value"] = anchor + e['elo']
            src = e.get('pairs') if e.get('pairs', {}).get('lo') is not None else e.get('trinomial')
            if src:
                ref["lo"] = None if src.get('lo') is None else anchor + src['lo']
                ref["hi"] = None if src.get('hi') is None else anchor + src['hi']
        elif e.get('bound'):
            ref["bound"] = {"side": e['bound']['side'], "value": anchor + e['bound']['elo']}
        s["anchored_elo"] = ref
    return s


def fmt_elo(x, inf='∞'):
    """None은 무한대 (점수 범위가 0% 아래·100% 위로 넘어감): 하한이면 '-∞', 상한이면 '+∞'로 넘겨 씀"""
    return inf if x is None else f"{x:+.0f}"


def print_summary(cond, summary, names):
    t = summary['total']
    if not t['n']:
        print("끝난 판이 없음")
        return
    print(f"\n{'=' * 72}\n{names[0]}  vs  {names[1]}   ({cond['limit']})")

    def line(label, x):
        return (f"  {label:<14} {x['w']}승 {x['d']}무 {x['l']}패 / {x['n']}판   점수율 {x['score']:.1%}"
                if x['n'] else f"  {label:<14} -")
    print(line("전체", t))
    print(line("engine1 백", summary['engine1_white']))
    print(line("engine1 흑", summary['engine1_black']))
    print("  오프닝별 (engine1 기준):")
    for k, v in summary['by_opening'].items():
        print(f"    {k:<24} {v['w']}-{v['d']}-{v['l']}  ({v['score']:.0%})")
    print(f"  메이트 승 {summary['mate_wins']} / 메이트 패 {summary['mate_losses']}")
    for key, label in (("time_losses", "시간패"), ("illegal_moves", "불법수·수 없음"),
                       ("engine_errors", "엔진 오류·충돌")):
        v = summary[key]
        print(f"  {label:<14} engine1 {v['engine1']} / engine2 {v['engine2']}")
    print("  종료 사유:", ', '.join(f"{k} {v}" for k, v in sorted(summary['terminations'].items())))
    print(f"  평균 대국 길이 {summary['avg_plies']} ply")
    for i, nm in ((1, names[0]), (2, names[1])):
        th = summary['think'][f'engine{i}']
        search = (f", 평균 깊이 {th['avg_depth']}, 수당 노드 {th['avg_nodes']:,}, NPS {th['nps']:,}"
                  if th.get('avg_depth') is not None and th.get('nps') else '')
        print(f"  생각 시간 {nm}: 평균 {th['avg']:.2f}s, 최대 {th['max']:.2f}s ({th['moves']}수){search}")
    env = summary.get('environment') or {}
    if env.get('load_mean') is not None:
        print(f"  실행 환경: 시스템 부하 평균 {env['load_mean']} 최대 {env['load_max']}, 일한 코어 평균 "
              f"{env['cpu_busy_cores_mean']} (1.5 넘은 판 {env['games_busy_over_1_5']})")

    e = summary['elo']
    print("\n  Elo 차이 (engine1 − engine2, 상대적인 값):")
    if e.get('elo') is not None:
        tri = e['trinomial']
        if tri.get('degenerate'):
            print(f"    {fmt_elo(e['elo'])}  95% 범위: 계산 불가 (모든 판이 같은 결과라 분산 0 — 판을 늘려야 함)")
        else:
            print(f"    {fmt_elo(e['elo'])}  95% 범위 {fmt_elo(tri['lo'], '-∞')} ~ {fmt_elo(tri['hi'], '+∞')}  "
                  f"(판을 독립으로 본 삼항 오차)")
        if e.get('pairs') and not e['pairs'].get('degenerate'):
            pr = e['pairs']
            print(f"    쌍 기준 {fmt_elo(pr['elo'])}  95% 범위 {fmt_elo(pr['lo'], '-∞')} ~ {fmt_elo(pr['hi'], '+∞')}  "
                  f"(같은 오프닝 두 판 = 한 쌍, {pr['pairs']}쌍)")
    else:
        b = e['bound']
        word = "이하" if b['side'] == 'upper' else "이상"
        print(f"    점수율 {e['score']:.0%} → Elo 차이는 무한대로 나와 값으로 쓸 수 없음. "
              f"한쪽 95% 경계: {fmt_elo(b['elo'])} {word} (무승부 없는 이항 분포 기준)")
    if e.get('los') is not None:
        print(f"    LOS(engine1이 더 강할 확률, 무승부 제외 정규 근사) {e['los']:.1%}")
    if e['games'] < 30:
        print(f"    ※ {e['games']}판은 표본이 작아 범위가 넓고 정규 근사도 거칠어요. 수십~수백 판이 필요해요.")
    if summary['unpaired_games']:
        print(f"    ※ 짝이 없는 판 {summary['unpaired_games']}개는 쌍 오차 계산에서 빠짐")
    a = summary.get('anchored_elo')
    if a:
        tag = "" if a['strength_applied'] else "  [강도 제한 적용이 확인되지 않음 — 참고 불가]"
        if 'value' in a:
            rng = (f" (범위 {a['lo']:.0f} ~ {a['hi']:.0f})" if a.get('lo') is not None and a.get('hi') is not None
                   else "")
            print(f"  상대 설정 Elo {a['anchor']} 기준 환산: 약 {a['value']:.0f}{rng}{tag}")
        else:
            word = "이하" if a['bound']['side'] == 'upper' else "이상"
            print(f"  상대 설정 Elo {a['anchor']} 기준 환산: {a['bound']['value']:.0f} {word}{tag}")
        print("    ※ 절대 Elo가 아님. 상대의 '설정 Elo'는 그 엔진이 정한 척도의 목표값이며 (Stockfish는 문서상\n"
              "      특정 시간 조건에서 CCRL 40/4 기준으로 보정), 이 대국의 시간·하드웨어에서 실제로 그 실력이라는\n"
              "      보장이 없음. FIDE 등 사람 레이팅과도 다른 척도.")
    print('=' * 72)


# ──────────────────────────────── 저장 ────────────────────────────────
CSV_FIELDS = ["round", "game_id", "variant", "game_index", "pair", "opening", "engine1_color", "white", "black",
              "result", "score1", "termination", "termination_detail", "culprit", "plies", "started", "finished",
              "duration_s", "load_start", "cpu_busy_cores",
              "white_avg_think", "white_max_think", "white_avg_depth", "white_nps",
              "black_avg_think", "black_max_think", "black_avg_depth", "black_nps", "moves"]


def save_outputs(paths, data):
    tmp = paths['json'] + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, paths['json'])              # 저장 도중 멈춰도 이전 파일이 깨지지 않게
    tmp = paths['csv'] + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        wr = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        wr.writeheader()
        for r in data['games']:
            row = {k: r.get(k) for k in CSV_FIELDS}
            for side in ('white', 'black'):
                st = r['think'][side]
                row.update({f"{side}_avg_think": st['avg'], f"{side}_max_think": st['max'],
                            f"{side}_avg_depth": st.get('avg_depth'), f"{side}_nps": st.get('nps')})
            row["moves"] = ' '.join(r['moves'])
            wr.writerow(row)
    os.replace(tmp, paths['csv'])


# ──────────────────────────────── 비교 ────────────────────────────────
def _rows_of(fn, d):
    """결과 파일 하나 → (표시 이름, 요약, engine1 옵션) 목록. 변형 실험이면 변형마다 한 줄"""
    label = d.get('label') or os.path.basename(fn)
    e1 = d['conditions']['engines'][0]['options']
    s = d['summary']
    if 'variants' in s:
        vopts = d['conditions'].get('variants', {})
        return [(f"{label}/{name}", sv, {**e1, **vopts.get(name, {})}) for name, sv in s['variants'].items()]
    return [(label, s, e1)]


def compare(files):
    runs = []
    for fn in files:
        with open(fn, encoding='utf-8') as f:
            runs.append((fn, json.load(f)))
    print(f"{'실험':<18} {'판':>3} {'승-무-패':>9} {'점수율':>6} {'Elo 차이 (95%)':>22} {'메이트승/패':>9} "
          f"{'시간패':>5} {'불법':>4} {'오류':>4} {'평균생각':>7} {'깊이':>5} {'NPS':>7} {'평균ply':>6}")
    rows = []
    for fn, d in runs:
        for label, s, opts in _rows_of(fn, d):
            rows.append((label, s, opts))
            t, e = s['total'], s.get('elo') or {}
            if not t['n']:
                print(f"{label:<18}   0판")
                continue
            if e.get('elo') is not None:
                src = e.get('pairs') if (e.get('pairs') or {}).get('lo') is not None else e.get('trinomial', {})
                elo = f"{fmt_elo(e['elo'])} ({fmt_elo(src.get('lo'), '-∞')}~{fmt_elo(src.get('hi'), '+∞')})"
            elif e.get('bound'):
                elo = f"{'≤' if e['bound']['side'] == 'upper' else '≥'}{fmt_elo(e['bound']['elo'])}"
            else:
                elo = '-'
            th = s['think']['engine1']
            dep = f"{th['avg_depth']:.2f}" if th.get('avg_depth') is not None else '-'
            nps = f"{th['nps']:,}" if th.get('nps') else '-'
            ply = f"{s['avg_plies']:.0f}" if s.get('avg_plies') is not None else '-'
            print(f"{label:<18} {t['n']:>3} {t['w']:>3}-{t['d']}-{t['l']:<3} {t['score']:>6.1%} {elo:>22} "
                  f"{s['mate_wins']:>4}/{s['mate_losses']:<4} {s['time_losses']['engine1']:>5} "
                  f"{s['illegal_moves']['engine1']:>4} {s['engine_errors']['engine1']:>4} "
                  f"{th['avg']:>6.2f}s {dep:>5} {nps:>7} {ply:>6}")
    # 실행 환경: 언제 돌렸는지, 다른 부하가 있었는지
    print("\n실행 환경:")
    spans = []
    for fn, d in runs:
        label = d.get('label') or os.path.basename(fn)
        c = d['conditions']
        env = (d['summary'].get('environment') if 'variants' not in d['summary']
               else d['summary'].get('environment')) or {}
        try:
            t0, t1 = parse_time(d['started']), parse_time(d['finished'])
            spans.append((label, t0, t1))
            when = f"{t0.strftime('%Y-%m-%d %H:%M:%S')} ~ {t1.strftime('%H:%M:%S')}"
        except (KeyError, ValueError):
            when = '시각 기록 없음'
        load = (f"부하 평균 {env.get('load_mean')} 최대 {env.get('load_max')}, 일한 코어 평균 {env.get('cpu_busy_cores_mean')}"
                if env.get('load_mean') is not None else "부하 기록 없음 (이전 버전의 결과 파일)")
        conc = c.get('concurrent_with')
        print(f"  {label:<16} {when}  CPU {c.get('cpu_count')}개  {load}"
              + (f"  ※ 시작할 때 다른 실험이 실행 중이었음: {conc}" if conc else ''))
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            a, b = spans[i], spans[j]
            overlap = (min(a[2], b[2]) - max(a[1], b[1])).total_seconds()
            if overlap > 0:
                print(f"  ※ {a[0]}와(과) {b[0]}의 실행 시간이 {overlap:.0f}초 겹침 → 같은 컴퓨터였다면 동시에 실행되어 "
                      f"CPU를 나눠 썼음 (탐색 깊이·시간 사용이 달라질 수 있음)")
    # 조건이 다르면 결과를 직접 비교할 수 없음 → 다른 항목을 알림
    keys = [("상대 엔진", lambda c: c['engines'][1]['name']),
            ("상대 옵션", lambda c: fmt_opts(c['engines'][1]['options'])),
            ("시간 조건", lambda c: c['limit']),
            ("오프닝 순서", lambda c: ' | '.join(c['openings_used'])),
            ("engine1 Hash", lambda c: c['engines'][0].get('hash_mb')),
            ("최대 ply", lambda c: c.get('max_plies')),
            ("CPU 수", lambda c: c.get('cpu_count')),
            ("운영체제·Python", lambda c: f"{c.get('os')} / {c.get('python')}")]
    diffs = []
    for name, get in keys:
        vals = {str(get(d['conditions'])) for _, d in runs}
        if len(vals) > 1:
            diffs.append(f"{name}: " + ' / '.join(sorted(vals)))
    print("\n비교 조건:", "모두 같음 (상대·상대 옵션·시간·오프닝·Hash·최대 ply·CPU·OS)" if not diffs else "")
    for x in diffs:
        print("  ※ 다름 —", x)
    print("실험 변수 (engine1 옵션):", ' | '.join(f"{label}: [{fmt_opts(opts)}]" for label, _, opts in rows))
    for fn, d in runs:                          # 변형 실험 파일에는 짝 비교가 들어 있음
        if d['summary'].get('paired'):
            print_paired(d['summary']['paired'], d['summary'].get('paired_names', ('A', 'B')))
    if len(rows) == 2 and not diffs and not any(d['summary'].get('paired') for _, d in runs):
        # 서로 다른 실행 두 개의 점수율 차이: 각 실험의 표준오차(쌍 기준이 있으면 그것)를 독립으로 보고 합침
        ses = []
        for _, s, _ in rows:
            e = s.get('elo') or {}
            src = e.get('pairs') if e.get('pairs') and not e['pairs'].get('degenerate') else e.get('trinomial')
            ses.append(src.get('se') if src and not src.get('degenerate') else None)
        s1, s2 = rows[0][1]['total']['score'], rows[1][1]['total']['score']
        if None not in ses and s1 is not None and s2 is not None:
            se = math.sqrt(ses[0] ** 2 + ses[1] ** 2)
            lo, hi = s2 - s1 - 1.96 * se, s2 - s1 + 1.96 * se
            verdict = "0을 포함 → 차이가 있다고 말할 수 없음" if lo <= 0 <= hi else "0을 벗어남 → 차이가 있을 가능성이 큼"
            print(f"점수율 차이 (2번째 − 1번째): {s2 - s1:+.1%}  95% 범위 {lo:+.1%} ~ {hi:+.1%}  ({verdict})")
    print("※ 범위가 겹치면 차이가 우연일 수 있음. 판 수가 적으면 더 그러함.")


def print_paired(p, names):
    a, b = names
    print(f"\n짝 비교 ({b} − {a}, 같은 오프닝·같은 색끼리 {p['pairs']}짝):")
    if p.get('se'):
        verdict = ("0을 포함 → 차이가 있다고 말할 수 없음" if p['lo'] <= 0 <= p['hi']
                   else "0을 벗어남 → 차이가 있을 가능성이 큼")
        print(f"  점수율 차이 {p['mean_diff']:+.1%}  95% 범위 {p['lo']:+.1%} ~ {p['hi']:+.1%}  ({verdict})")
    else:
        print(f"  점수율 차이 {p['mean_diff']:+.1%}  (짝이 너무 적어 범위를 계산할 수 없음)")
    print(f"  {b}가 더 나은 짝 {p['b_better']}, 같은 결과 {p['same']}, {a}가 더 나은 짝 {p['a_better']}  "
          f"→ 부호 검정 p = {p['sign_test_p']:.2f} (0.05보다 크면 우연으로 설명 가능)")
    for col, kr in (('white', '백'), ('black', '흑')):
        if col in p.get('by_color', {}):
            c = p['by_color'][col]
            print(f"  engine1이 {kr}일 때: 차이 {c['mean_diff']:+.1%} ({c['pairs']}짝)")
    print("  가정: 짝끼리 독립, 평균 차이의 정규 근사. 짝이 수십 개뿐이면 범위는 대략적인 값.")


# ──────────────────────────────── 패배 원인 분석 ────────────────────────────────
MATE_CP = 10000


def _cp(score, color):
    return score.pov(color).score(mate_score=MATE_CP)


def _fmt_cp(v):
    if abs(v) >= MATE_CP - 200:
        return f"{'-' if v < 0 else '+'}M{MATE_CP - abs(v)}"
    return f"{v / 100:+.2f}"


def _king_zone_attackers(board, color):
    """color 킹 주변(킹 칸 + 인접 칸)을 공격하는 상대 기물(폰·킹 제외) 수"""
    k = board.king(color)
    zone = chess.SquareSet(chess.BB_KING_ATTACKS[k]) | chess.SquareSet.from_square(k)
    att = set()
    for z in zone:
        for a in board.attackers(not color, z):
            if board.piece_type_at(a) not in (chess.PAWN, chess.KING):
                att.add(a)
    return len(att)


def _material(board, color):
    val = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    return sum(v * (len(board.pieces(pt, color)) - len(board.pieces(pt, not color))) for pt, v in val.items())


def analyze_results(args):
    """끝난 실험(JSON)의 engine1 패배 대국을 분석 엔진(기본 Stockfish, 강도 제한 없음)으로 돌려 봄.
    ① 모든 수 직전 국면을 고정 깊이로 평가 → engine1의 수마다 '평가 손실'(둔 직전 − 둔 직후)
    ② 대국마다 결정적 실수 = 아직 크게 지지 않은(−3.00 이상) 국면에서 손실이 가장 큰 수
    ③ 그 국면을 engine1로 다시 탐색: 대국과 비슷한 시간 / 훨씬 긴 시간 / King Safety를 반대로
       · 긴 시간에 좋은 수를 찾으면 → 탐색 깊이(시간) 문제
       · 긴 시간에도 못 찾고, 둔 뒤 몇 수 안의 메이트면 → 전술(메이트) 탐색 한계
       · 그 외 → 평가(위치 판단) 문제 '후보'  — 분석 엔진이 더 나은 수를 안다는 것만으로 평가 오류라 단정하지 않음
    추정 원인은 이 규칙으로 붙인 꼬리표일 뿐이며, 사람이 확인할 출발점임."""
    with open(args.analyze, encoding='utf-8') as f:
        data = json.load(f)
    e1 = data['conditions']['engines'][0]
    cmd = args.analyze_engine or e1['cmd']
    depth, short_t, long_t = args.analyze_depth, args.analyze_short, args.analyze_long
    sf = chess.engine.SimpleEngine.popen_uci(shlex.split(args.analyzer), timeout=30)
    games = [g for g in data['games'] if g['score1'] == 0]
    if args.analyze_max:
        games = games[:args.analyze_max]
    variants = data['conditions'].get('variants')
    rows = []
    print(f"분석: {args.analyze}  engine1 패배 {len(games)}판, 분석 엔진 {sf.id.get('name')} depth {depth}, "
          f"재탐색 {short_t}s / {long_t}s")
    try:
        for g in games:
            opts = dict(e1['options'])
            if variants and g.get('variant'):
                opts.update(variants[g['variant']])
            me = chess.WHITE if g['engine1_color'] == 'white' else chess.BLACK
            board = chess.Board()
            evals, bests, boards = [], [], []
            n_open = len(g['opening_moves'].split())
            for u in g['moves'] + [None]:
                if board.is_game_over():
                    evals.append(-MATE_CP if board.is_checkmate() and board.turn == me else
                                 MATE_CP if board.is_checkmate() else 0)
                    bests.append(None)
                else:
                    info = sf.analyse(board, chess.engine.Limit(depth=depth), game=object())
                    evals.append(_cp(info['score'], me))
                    bests.append(info['pv'][0] if info.get('pv') else None)
                boards.append(board.copy())
                if u is not None:
                    board.push_uci(u)
            mine = [i for i in range(n_open, len(g['moves'])) if boards[i].turn == me]
            losses = {i: evals[i] - evals[i + 1] for i in mine}
            cand = [i for i in mine if evals[i] >= -300] or mine
            key = max(cand, key=lambda i: losses[i])
            kb = boards[key]
            played = chess.Move.from_uci(g['moves'][key])
            castled = any(boards[i].is_castling(chess.Move.from_uci(g['moves'][i])) for i in mine if i <= key)
            final = boards[-1]
            row = {"round": g['round'], "variant": g.get('variant'), "color": g['engine1_color'],
                   "opening": g['opening'], "ply": key, "fen": kb.fen(), "played": kb.san(played),
                   "best": kb.san(bests[key]) if bests[key] else '-', "eval_before": evals[key],
                   "eval_after": evals[key + 1], "loss": losses[key], "castled_before": castled,
                   "king_file": chess.FILE_NAMES[chess.square_file(kb.king(me))],
                   "zone_attackers": _king_zone_attackers(kb, me), "material": _material(kb, me),
                   "mated_king_sq": chess.square_name(final.king(me)) if final.is_checkmate() else None,
                   "big_losses": sum(1 for i in mine if losses[i] >= 150),
                   "king_safety_option": opts.get('KingSafety', 'default')}
            # 같은 국면을 engine1로 다시 탐색
            def research(o, t):
                eng = chess.engine.SimpleEngine.popen_uci(shlex.split(cmd), timeout=30)
                try:
                    if o:
                        eng.configure(o)
                    r = eng.play(kb, chess.engine.Limit(time=t), game=object(), info=chess.engine.INFO_ALL)
                    return r.move, r.info.get('depth')
                finally:
                    eng.quit()

            def after_eval(mv):
                if mv == played:
                    return evals[key + 1]
                b2 = kb.copy()
                b2.push(mv)
                if b2.is_game_over():
                    return MATE_CP if b2.is_checkmate() else 0
                return -_cp(sf.analyse(b2, chess.engine.Limit(depth=depth), game=object())['score'], not me)
            try:
                m_short, d_short = research(opts, short_t)
                m_long, d_long = research(opts, long_t)
                flip = dict(opts)
                flip['KingSafety'] = not (opts.get('KingSafety', args.analyze_ks_default))
                m_flip, _ = research(flip, short_t)
                ev_long = after_eval(m_long)
                ev_flip = after_eval(m_flip)
                row.update({"re_short": kb.san(m_short), "re_short_depth": d_short, "re_long": kb.san(m_long),
                            "re_long_depth": d_long, "re_long_eval": ev_long, "re_flip": kb.san(m_flip),
                            "re_flip_eval": ev_flip})
                fixed_by_time = evals[key] - ev_long < max(80, losses[key] // 3)
                mate_dist = MATE_CP - abs(evals[key + 1]) if evals[key + 1] <= -(MATE_CP - 200) else None
                if losses[key] < 100:
                    cause = "한 수의 큰 실수 없음 (서서히 밀림: 위치 판단·깊이 누적)"
                elif fixed_by_time:
                    cause = f"탐색 깊이 부족 (긴 탐색 d{d_long}은 {kb.san(m_long)})"
                elif mate_dist is not None:
                    cause = f"메이트 위협 미탐지 (둔 뒤 M{mate_dist}, 긴 탐색도 못 찾음)"
                else:
                    cause = "평가(위치 판단) 후보 — 긴 탐색도 같은 계열의 수"
                row["cause"] = cause
                row["flip_helps"] = evals[key] - ev_flip < max(80, losses[key] // 3) and m_flip != played
            except Exception as e:                  # 재탐색 실패는 기록만
                row["cause"] = f"재탐색 실패: {type(e).__name__}"
                row["flip_helps"] = None
            tags = []
            if not castled:
                tags.append("캐슬링 안 함")
            if row['zone_attackers'] >= 2:
                tags.append(f"킹 주변 공격 기물 {row['zone_attackers']}")
            if row['material'] >= 2:
                tags.append(f"물질 +{row['material']}")
            if row['material'] <= -2:
                tags.append(f"물질 {row['material']}")
            row["tags"] = tags
            rows.append(row)
            print(f"  {g['round']:>3} {row['variant'] or '':<7} {g['engine1_color'][0]} ply {key:>3} "
                  f"{row['played']:<7} (best {row['best']:<7}) {_fmt_cp(evals[key])}→{_fmt_cp(evals[key + 1])} "
                  f"{row['cause']}  [{', '.join(tags)}]", flush=True)
    finally:
        sf.quit()
    out = os.path.splitext(args.analyze)[0] + '_analysis.json'
    causes = {}
    for r in rows:
        k = r['cause'].split(' (')[0]
        causes[k] = causes.get(k, 0) + 1
    summary = {"losses": len(rows), "causes": causes,
               "not_castled": sum(not r['castled_before'] for r in rows),
               "zone_attackers_2plus": sum(r['zone_attackers'] >= 2 for r in rows),
               "material_up_2plus": sum(r['material'] >= 2 for r in rows),
               "flip_helps": sum(bool(r.get('flip_helps')) for r in rows),
               "mean_loss_cp": round(sum(min(r['loss'], 2000) for r in rows) / max(1, len(rows))),
               "mean_big_losses_per_game": round(sum(r['big_losses'] for r in rows) / max(1, len(rows)), 2)}
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({"source": args.analyze, "analyzer": args.analyzer, "depth": depth, "summary": summary,
                   "rows": rows}, f, ensure_ascii=False, indent=1)
    print("\n요약:", json.dumps(summary, ensure_ascii=False))
    print("표 (대국 | FEN | 엔진 선택 | 더 나은 수 | 추정 원인):")
    for r in rows:
        print(f"| {r['round']}{'/' + r['variant'] if r['variant'] else ''} | {r['fen']} | {r['played']} | {r['best']} | "
              f"{r['cause']} |")
    print("저장:", out)


# ──────────────────────────────── main ────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="UCI 엔진 자동 대국")
    ap.add_argument('--engine1')
    ap.add_argument('--engine2')
    ap.add_argument('--opt1', action='append', help="engine1 UCI 옵션 NAME=VALUE (여러 번)")
    ap.add_argument('--opt2', action='append', help="engine2 UCI 옵션 NAME=VALUE (여러 번)")
    ap.add_argument('--games', type=int, default=10)
    ap.add_argument('--tc', default='10+0.1', help="기본시간+증가 (초), 예: 10+0.1")
    ap.add_argument('--movetime', type=int, help="한 수 고정 시간(ms) — 지정하면 --tc 무시")
    ap.add_argument('--depth', type=int, help="한 수 고정 깊이 — 지정하면 --tc 무시")
    ap.add_argument('--pgn', default='match.pgn')
    ap.add_argument('--json', help="결과 JSON (기본: PGN 이름.json)")
    ap.add_argument('--csv', help="판별 CSV (기본: PGN 이름.csv)")
    ap.add_argument('--label', help="실험 이름 (PGN Event, 비교 표에 표시)")
    ap.add_argument('--seed', type=int, help="오프닝 순서를 이 시드로 섞음 (없으면 고정 순서)")
    ap.add_argument('--no-strength-check', action='store_true', help="강도 제한 적용 확인을 건너뜀")
    ap.add_argument('--variant', action='append', metavar='NAME:OPT=VAL[,OPT=VAL]',
                    help="engine1의 설정 변형 (2개 이상). 같은 실행 안에서 번갈아 순차 대국하고 짝 비교를 냄")
    ap.add_argument('--allow-concurrent', action='store_true',
                    help="다른 match.py 실험이 실행 중이어도 시작 (기본: 거부. 성능 비교에는 쓰지 말 것)")
    ap.add_argument('--compare', nargs='+', metavar='JSON', help="결과 JSON 여러 개를 비교하고 끝냄")
    ap.add_argument('--analyze', metavar='JSON', help="결과 JSON의 engine1 패배 대국을 분석 엔진으로 분석하고 끝냄")
    ap.add_argument('--analyzer', default='stockfish', help="분석 엔진 명령 (기본 stockfish, 강도 제한 없이 사용)")
    ap.add_argument('--analyze-engine', help="재탐색에 쓸 engine1 명령 (기본: JSON에 기록된 명령)")
    ap.add_argument('--analyze-depth', type=int, default=12)
    ap.add_argument('--analyze-short', type=float, default=0.25, help="재탐색 시간(초): 대국과 비슷하게")
    ap.add_argument('--analyze-long', type=float, default=5.0, help="재탐색 시간(초): 길게")
    ap.add_argument('--analyze-max', type=int, help="앞에서부터 이 판 수만 분석")
    ap.add_argument('--analyze-ks-default', action='store_true',
                    help="engine1의 KingSafety 기본값이 true였던 실험이면 지정 (옵션 기록이 없을 때 반대 설정을 정하는 데 씀)")
    args = ap.parse_args()
    if args.compare:
        compare(args.compare)
        return
    if args.analyze:
        analyze_results(args)
        return
    if not (args.engine1 and args.engine2):
        ap.error("--engine1과 --engine2가 필요해요 (또는 --compare)")
    base, _, inc = args.tc.partition('+')
    args.base, args.inc = float(base), float(inc or 0)
    stem = os.path.splitext(args.pgn)[0]
    paths = {"pgn": args.pgn, "json": args.json or stem + '.json', "csv": args.csv or stem + '.csv'}

    openings = list(OPENINGS)
    if args.seed is not None:
        random.Random(args.seed).shuffle(openings)
    if args.movetime:
        limit, pgn_tc = f"movetime {args.movetime}ms", "-"
    elif args.depth:
        limit, pgn_tc = f"depth {args.depth}", "-"
    else:
        limit, pgn_tc = f"{args.tc}s", f"{args.base:g}+{args.inc:g}"

    # 변형: 같은 engine1 프로그램에 UCI 옵션만 다르게 준 설정들 (예: KingSafety 켬/끔). 별도의 엔진이 아님.
    variants = []
    for item in args.variant or []:
        name, _, optstr = item.partition(':')
        variants.append((name.strip(), parse_opts([o for o in optstr.split(',') if o.strip()])))
    if len({n for n, _ in variants}) != len(variants) or len(variants) == 1:
        ap.error("--variant는 이름이 서로 다른 것을 2개 이상 주어야 해요 (예: --variant off:KingSafety=false --variant on:KingSafety=true)")

    # 다른 match.py 실험과 동시에 돌리지 않음 (CPU를 나눠 쓰면 탐색 깊이가 달라져 비교가 흐려짐)
    other = running_match()
    if other and not args.allow_concurrent:
        sys.exit(f"다른 대국 실험이 실행 중이에요 (pid {other.get('pid')}, {other.get('label')}, 시작 {other.get('started')}).\n"
                 f"끝난 뒤 다시 실행하세요. 성능 비교가 목적이 아니라면 --allow-concurrent 로 강제할 수 있어요 "
                 f"(결과 파일에 동시 실행으로 기록됨).")
    experiment_id = f"{args.label or 'match'}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid() % 10000:04d}"
    holds_lock = False
    if not other:
        holds_lock = write_lock({"pid": os.getpid(), "label": args.label, "experiment_id": experiment_id,
                                 "started": now_iso()})

    base_opts = parse_opts(args.opt1)
    e1_players, players_all = {}, []
    try:
        for vname, vopts in (variants or [(None, {})]):
            nm, cmd = 'engine1', args.engine1
            e1_players[vname] = Player(cmd, {**base_opts, **vopts}, 'engine1')
            players_all.append(e1_players[vname])
        nm, cmd = 'engine2', args.engine2
        opp = Player(cmd, parse_opts(args.opt2), 'engine2')
        players_all.append(opp)
    except Exception as e:                      # 엔진을 못 띄우거나 옵션이 틀림 (없는 옵션·범위 밖 값 등)
        for p in players_all:
            p.close()
        if holds_lock:
            release_lock()
        sys.exit(f"{nm} 시작 실패 ({cmd}): {type(e).__name__}: {e}")
    first = players_all[0]
    if first.name == opp.name:
        for p in players_all[:-1]:
            p.name += ' (1)'
        opp.name += ' (2)'
    names = [first.name, opp.name]
    desc = [first.describe(), opp.describe()]
    desc[0]['options'] = base_opts              # 변형 옵션은 conditions.variants에 따로 기록
    if not args.no_strength_check:
        for i, p in enumerate((first, opp)):
            desc[i]['strength'] = strength_check(p, openings)
            for note in desc[i]['strength'].get('notes', []):
                print(f"※ {p.name}: {note}")
    cond = {"experiment_id": experiment_id, "limit": limit, "pgn_timecontrol": pgn_tc, "base_s": args.base,
            "inc_s": args.inc, "movetime_ms": args.movetime, "depth": args.depth, "games_requested": args.games,
            "seed": args.seed, "openings_used": [o[0] for o in openings], "max_plies": MAX_PLIES,
            "engines": desc, "variants": {n: o for n, o in variants} or None,
            "schedule": "sequential; variants interleaved per opening (A B B A / B A A B)" if variants else "sequential",
            "python": platform.python_version(), "python_chess": chess.__version__,
            "os": platform.platform(), "machine": platform.machine(), "processor": platform.processor() or None,
            "cpu_count": os.cpu_count(), "load_at_start": load1(),
            "concurrent_with": (f"pid {other.get('pid')} {other.get('label')}" if other else None),
            "match_tool": MATCH_VERSION}
    if args.games % 2:
        print("※ 판 수가 홀수라 마지막 오프닝은 한 색으로만 둠 (쌍 오차 계산에서 빠짐)")
    for i, d in enumerate(desc):
        st = d.get('strength', {})
        extra = ''
        if st.get('requested'):
            pr = st.get('probe')
            extra = (f", 강도 제한 {'확인됨' if st.get('applied') else '확인 안 됨'}"
                     + (f" (오프닝 {pr['positions']}국면 중 {pr['different_moves']}개에서 제한 없는 설정과 다른 수)"
                        if pr else ''))
        print(f"engine{i + 1}: {d['name']}  [{fmt_opts(d['options'])}]  Hash {d['hash_mb']}MB{extra}")
    for n, o in variants:
        print(f"  변형 {n}: [{fmt_opts(o)}]")
    print(f"실험 ID {experiment_id}  CPU {os.cpu_count()}개, 시작 시 부하 {cond['load_at_start']}"
          + ("  ※ 다른 실험과 동시 실행 중" if other else ''))
    if cond['load_at_start'] is not None and cond['load_at_start'] > 0.7:
        print("※ 시작 시 시스템 부하가 높음 — 다른 프로그램이 CPU를 쓰고 있으면 결과 비교가 흐려질 수 있음")
    per = f"변형마다 {args.games}판 (총 {args.games * len(variants)}판, 오프닝마다 변형 순서를 번갈아 순차 실행)" \
        if variants else f"{args.games}판"
    print(f"{per}, {limit}, 오프닝 {'시드 ' + str(args.seed) if args.seed is not None else '고정 순서'}\n")

    # 대국 순서: 오프닝마다 [백, 흑] 두 판. 변형이 있으면 오프닝마다 A B B A / B A A B 로 번갈아
    # (먼저 두는 쪽·나중에 두는 쪽이 한 변형에 몰리지 않게)
    schedule = []
    vnames = [n for n, _ in variants] or [None]
    for pr in range((args.games + 1) // 2):
        order = vnames if pr % 2 == 0 else vnames[::-1]
        opening = openings[pr % len(openings)]
        schedule += [(v, opening, 0, 2 * pr) for v in order]
        if 2 * pr + 1 < args.games:
            schedule += [(v, opening, 1, 2 * pr + 1) for v in reversed(order)]

    def build_summary():
        if not variants:
            return summarize(records, desc)
        out = {"variants": {n: summarize([r for r in records if r['variant'] == n], desc) for n in vnames},
               "environment": environment_stats(records)}
        if len(vnames) >= 2:
            a, b = vnames[0], vnames[-1]
            out["paired"] = paired_stats([r for r in records if r['variant'] == a],
                                         [r for r in records if r['variant'] == b])
            out["paired_names"] = [a, b]
        return out

    records = []
    data = {"format": "match.py results", "label": args.label, "experiment_id": experiment_id,
            "started": now_iso(), "completed": False, "conditions": cond, "games": records}
    t_start = time.time()
    interrupted = None
    try:
        with open(paths['pgn'], 'w', encoding='utf-8') as pgn_file:
            for n, (vname, opening, white_idx, g_index) in enumerate(schedule, 1):
                players = [e1_players[vname], opp]
                rec, board = play_game(players, opening, white_idx, args, n,
                                       {"variant": vname, "game_index": g_index, "experiment_id": experiment_id})
                records.append(rec)
                print(make_pgn(rec, board, players, white_idx, args, cond), file=pgn_file, end='\n\n', flush=True)
                print(f"  {n:>3}. {rec['white']:<24} - {rec['black']:<24} {rec['result']:<8} "
                      f"{rec['plies']:>3} ply  {rec['opening']:<24} {rec['termination_detail']}", flush=True)
                if rec['culprit'] is not None:          # 문제를 일으킨 엔진은 다시 띄움
                    p = players[rec['culprit'] - 1]
                    try:
                        p.restart()
                        print(f"       ↳ {p.name} 다시 시작 ({p.restarts}번째)")
                    except Exception as e:
                        interrupted = f"{p.name} 재시작 실패: {type(e).__name__}: {e}"
                        print("중단:", interrupted)
                        break
                data["duration_s"] = round(time.time() - t_start, 1)
                data["summary"] = build_summary()
                save_outputs(paths, data)
                if holds_lock:
                    try:
                        os.utime(LOCK_PATH)             # 살아 있다는 표시
                    except OSError:
                        pass
    except KeyboardInterrupt:
        interrupted = "사용자 중단 (Ctrl+C)"
        print("\n중단됨 — 끝난 판까지 저장합니다")
    except Exception as e:                              # 예상 못 한 오류: 끝난 판은 저장하고 알림
        interrupted = f"{type(e).__name__}: {e}"
        print("\n오류로 중단:", interrupted)
    finally:
        for p in players_all:
            p.close()
        if holds_lock:
            release_lock()
        data["completed"] = interrupted is None and len(records) == len(schedule)
        data["interrupted"] = interrupted
        data["finished"] = now_iso()
        data["duration_s"] = round(time.time() - t_start, 1)
        data["restarts"] = {"engine1": sum(p.restarts for p in players_all[:-1]), "engine2": opp.restarts}
        data["summary"] = build_summary()
        save_outputs(paths, data)
    if variants:
        for n in vnames:
            print_summary(cond, data["summary"]["variants"][n], [f"{names[0]} [{n}]", names[1]])
        if data["summary"].get("paired"):
            print_paired(data["summary"]["paired"], data["summary"]["paired_names"])
        env = data["summary"]["environment"]
        print(f"\n실행 환경: 부하 평균 {env['load_mean']} 최대 {env['load_max']}, 일한 코어 평균 "
              f"{env['cpu_busy_cores_mean']} 최대 {env['cpu_busy_cores_max']} (1.5 넘은 판 {env['games_busy_over_1_5']})")
    else:
        print_summary(cond, data["summary"], names)
    print(f"총 {data['duration_s']:.0f}s,  기보 {paths['pgn']}  결과 {paths['json']}  표 {paths['csv']}")
    if interrupted:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
