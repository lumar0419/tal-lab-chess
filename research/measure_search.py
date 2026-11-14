"""Paired, sequential benchmarks across clean Tal Lab source checkouts.

Run from the project root. The independent reference is used only offline.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {
    'default': {},
    'lmr': {'lmr': True},
    'quiet_checks': {'qsearch_quiet_checks': True},
    'ordering': {'tactical_ordering': True},
    'aspiration': {'aspiration': True},
    'pvs_off': {'pvs': False},
    'cache_off': {'eval_cache_size': 0},
    'root_order_off': {'reuse_root_order': False},
}

RUN = """
import json, sys, time
from board import Board
from search import Searcher
from evaluate import clear_pawn_cache
task=json.load(sys.stdin)
clear_pawn_cache()
board=Board() if task['history'] is not None else Board(task['fen'])
for move in task['history'] or []:
    board.push_uci(move)
assert board.fen()==task['fen']
snapshot=board.snapshot()
search=Searcher(tt_size=60000)
for key,value in task['flags'].items():
    if not hasattr(search,key):
        raise ValueError(key)
    setattr(search,key,value)
groups=[]
begin=time.perf_counter()
search.search(board,max_depth=task['depth'],multipv=task['multipv'],
              time_limit=task['seconds'], full_time=True,
              on_info=(lambda info: groups.append([info])) if task['multipv']==1 else None,
              on_multipv=groups.append if task['multipv']>1 else None)
elapsed=time.perf_counter()-begin
assert board.snapshot()==snapshot
iterations=[]
for group in groups:
    lines=[]
    for line in group:
        assert line.pv
        probe=Board(task['fen'])
        for move in line.pv:
            assert move in probe.legal_moves(), (task['fen'], line.pv)
            probe.make_move(move)
        lines.append({'move':line.pv[0].uci(),'score':line.score,
                      'pv':[move.uci() for move in line.pv]})
    iterations.append({'depth':group[0].depth,'seconds':max(x.seconds for x in group),
                       'lines':lines})
print(json.dumps({'elapsed':elapsed,'nodes':search.nodes,'iterations':iterations,
                  'lmr_probes':search.lmr_probes,'lmr_researches':search.lmr_researches,
                  'pvs_probes':search.pvs_probes,'pvs_researches':search.pvs_researches,
                  'aspiration_probes':search.aspiration_probes,
                  'aspiration_researches':search.aspiration_researches}))
"""


def run_search(source, fen, depth, multipv, seconds, flags=None, history=None):
    task = dict(fen=fen, depth=depth, multipv=multipv, seconds=seconds,
                flags=flags or {}, history=history)
    result = subprocess.run([sys.executable, '-c', RUN], input=json.dumps(task),
                            cwd=source, text=True, capture_output=True,
                            check=True, timeout=seconds + 8 if seconds else 90)
    return json.loads(result.stdout)


def stockfish_line(info, turn):
    score = info['score'].pov(turn)
    return {'move': info['pv'][0].uci(), 'cp': score.score(), 'mate': score.mate(),
            'depth': info['depth'], 'seconds': info.get('time'),
            'nodes': info.get('nodes'), 'pv': [m.uci() for m in info['pv']]}


def compare_reference(engine, fen, seconds, historical=None):
    import chess
    import chess.engine
    board = chess.Board(fen)
    limit = chess.engine.Limit(time=seconds)
    engine.configure({'Clear Hash': None})
    choices = engine.analyse(board, limit, multipv=3)
    result = {'candidates': [stockfish_line(info, board.turn) for info in choices]}
    if historical:
        engine.configure({'Clear Hash': None})
        forced = engine.analyse(board, limit, root_moves=[chess.Move.from_uci(historical)])
        result['forced_historical'] = stockfish_line(forced, board.turn)
    return result


def accepted_mates(fen, max_plies):
    """Independent exhaustive AND/OR proof for the small synthetic mate suite."""
    import chess
    board = chess.Board(fen)
    attacker = board.turn

    @lru_cache(maxsize=None)
    def wins(fen, plies):
        position = chess.Board(fen)
        if position.is_checkmate():
            return position.turn != attacker
        if not plies or position.is_game_over():
            return False
        legal = list(position.legal_moves)

        def child(move):
            position.push(move)
            result = wins(position.fen(), plies - 1)
            position.pop()
            return result

        return (any if position.turn == attacker else all)(child(move) for move in legal)

    for plies in range(1, max_plies + 1, 2):
        accepted = []
        for move in board.legal_moves:
            board.push(move)
            if wins(board.fen(), plies - 1):
                accepted.append(move.uci())
            board.pop()
        if accepted:
            if plies != max_plies:
                raise ValueError((fen, plies, max_plies))
            return accepted
    raise ValueError(f'No forced mate in {max_plies} plies: {fen}')


def last(run):
    return run['iterations'][-1] if run['iterations'] else {'depth': 0, 'lines': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, default=ROOT)
    parser.add_argument('--seconds', type=float, default=0.75)
    parser.add_argument('--depth', type=int, default=9)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--mode', choices=('timed', 'fixed', 'ablation'), default='timed')
    parser.add_argument('--stockfish')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    tactics = json.loads((ROOT / 'research/tactics.json').read_text())
    for case in tactics:
        case['accepted'] = accepted_mates(case['fen'], case['mate_plies'])
    historical = json.loads((ROOT / 'master_sacrifice_cases.json').read_text())['positions']
    tal = json.loads((ROOT / 'tal_positions.json').read_text())['positions']
    historical.extend({'id': p['id'], 'fen': p['fen'], 'historical_uci': p['tal_move']}
                      for p in tal if p['featured'])
    cases = tactics + historical + [
        {'id': 'opening', 'fen': 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'},
        {'id': 'kiwipete', 'fen': 'r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1'},
    ]
    settings = ([(name, args.candidate, flags) for name, flags in CONFIGS.items()]
                if args.mode == 'ablation' else
                [('baseline', args.baseline, {}), ('candidate', args.candidate, {})])
    report = {'platform': platform.platform(), 'python': platform.python_version(),
              'mode': args.mode, 'time_cap_seconds': args.seconds, 'max_depth': args.depth,
              'repeats': args.repeats, 'configs': [name for name, _, _ in settings], 'cases': []}
    try:
        if args.stockfish:
            import chess.engine
            engine = chess.engine.SimpleEngine.popen_uci(args.stockfish)
            engine.configure({'Threads': 1, 'Hash': 32})
            report['reference'] = {'id': engine.id, 'seconds': 0.4, 'threads': 1, 'hash_mb': 32}
        else:
            engine = None
        for case in cases:
            row = {k: case[k] for k in ('id', 'fen', 'accepted', 'historical_uci') if k in case}
            if engine and 'historical_uci' in row:
                row['reference'] = compare_reference(engine, case['fen'], .4, row['historical_uci'])
            row['multipv'] = 1 if args.mode == 'ablation' or 'accepted' in row else 3
            rows = {name: [] for name, _, _ in settings}
            for repeat in range(args.repeats):
                order = settings[repeat % len(settings):] + settings[:repeat % len(settings)]
                for name, source, flags in order:
                    rows[name].append(run_search(source, case['fen'], args.depth,
                                                 row['multipv'], args.seconds, flags))
            row['runs'] = rows
            for runs in rows.values():
                for run in runs:
                    lines = last(run)['lines']
                    if 'accepted' in row:
                        run['tactical_correct'] = bool(lines and lines[0]['move'] in row['accepted']
                                                       and lines[0]['score'] == 100000 - case['mate_plies'])
                    if 'historical_uci' in row:
                        run['historical_rank'] = next((i for i, x in enumerate(lines, 1)
                                                      if x['move'] == row['historical_uci']), None)
                    if 'reference' in row:
                        run['reference_top1_match'] = bool(lines and
                            lines[0]['move'] == row['reference']['candidates'][0]['move'])
            report['cases'].append(row)
            print(case['id'], {k: statistics.median(last(r)['depth'] for r in runs)
                               for k, runs in rows.items()}, flush=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    finally:
        if args.stockfish and 'engine' in locals():
            engine.quit()


if __name__ == '__main__':
    main()
