"""Replay supplied PGNs with two rules implementations; measure fresh searches.

Run with --engine pointing to the untouched v0.9.3 checkout for the baseline.
All centipawns and mate scores in the output are from White's perspective.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import chess
import chess.engine
import chess.pgn

FOCUS = {1: {19, 21, 29, 33, 37}, 2: {8, 12, 14, 20, 22, 24, 26}}
PASSED = {64, 66, 68, 70, 80, 82, 84, 92, 94}


def replay(path):
    from board import Board
    games, cases = [], []
    with open(path, encoding='utf-8') as stream:
        while (game := chess.pgn.read_game(stream)) is not None:
            if game.errors:
                raise ValueError(game.errors)
            index = len(games) + 1
            oracle, board, moves, positions = game.board(), Board(game.board().fen()), [], []
            for ply, move in enumerate(game.mainline_moves(), 1):
                if move not in oracle.legal_moves or board.parse_uci(move.uci()) is None:
                    raise ValueError((index, ply, move))
                before = oracle.fen(en_passant='fen')
                if before != board.fen():
                    raise AssertionError((index, ply, before, board.fen()))
                san = oracle.san(move)
                if ply in FOCUS[index] or (index == 2 and ply in PASSED):
                    cases.append(dict(id=f'g{index}_ply{ply}', game=index, ply=ply,
                        fen=before, moves=list(moves), played=move.uci(), san=san,
                        kind='passed' if index == 2 and ply in PASSED else 'diagnostic',
                        multipv=index))
                oracle.push(move)
                board.push_uci(move.uci())
                moves.append(move.uci())
                assert oracle.fen(en_passant='fen') == board.fen()
                positions.append(dict(ply=ply, san=san, uci=move.uci(), fen=board.fen()))
            games.append(dict(game=index, plies=len(moves), final_fen=board.fen(),
                result=game.headers['Result'], oracle_result=oracle.result(),
                checkmate=oracle.is_checkmate(), positions=positions))
    return games, cases


def tal(case, seconds=None, nodes=None, profile='tactical', trace_limit=0):
    from board import Board
    import evaluate
    from search import Searcher
    from research.pruning_trace import PruningTrace
    board = Board()
    for move in case['moves']:
        board.push_uci(move)
    assert board.fen() == case['fen']
    before = board.snapshot()
    engine = Searcher()
    engine.set_tactical(profile == 'tactical')
    engine.lmr = profile == 'conservative'
    trace = PruningTrace(engine, limit=trace_limit) if trace_limit else None
    if trace:
        engine.selective_trace = trace
    iterations = []
    sign = 1 if board.side == 0 else -1
    def collect(group):
        iterations.append(dict(depth=group[0].depth, nodes=engine.nodes,
            seconds=group[-1].seconds, lines=[dict(score_white=sign*i.score,
            pv=[m.uci() for m in i.pv]) for i in group]))
    start = time.perf_counter()
    move, score = engine.search(board, max_depth=64, time_limit=seconds, node_limit=nodes,
        full_time=True, multipv=case['multipv'],
        on_info=(lambda i: collect([i])) if case['multipv']==1 else None,
        on_multipv=collect if case['multipv'] > 1 else None)
    elapsed = time.perf_counter()-start
    assert before == board.snapshot()
    terms, phase, dead = evaluate.eval_terms(board)
    result = dict(move=move.uci() if move else None, score_white=sign*score,
        nodes=engine.nodes, elapsed=elapsed, nps=engine.nodes/elapsed,
        completed_depth=iterations[-1]['depth'] if iterations else 0,
        iterations=iterations, static_white=evaluate.evaluate_white(board),
        terms=terms, phase=phase, dead=dead, statistics=dict(engine.sel_stats))
    if trace:
        result.update(trace=trace.events, trace_dropped=trace.dropped)
    return result


def reference(engine, case, seconds, nodes):
    board = chess.Board()
    for move in case['moves']:
        board.push_uci(move)
    def analyze(root_moves=None, multipv=1):
        engine.configure({'Clear Hash':None})
        limit = chess.engine.Limit(nodes=nodes) if nodes else chess.engine.Limit(time=seconds)
        start = time.perf_counter()
        rows = engine.analyse(board, limit, root_moves=root_moves, multipv=multipv)
        elapsed = time.perf_counter()-start
        return [dict(depth=i.get('depth'), nodes=i.get('nodes'), nps=i.get('nps'),
            reported_seconds=i.get('time'), elapsed=elapsed,
            score_white=i['score'].white().score(mate_score=30000),
            mate_white=i['score'].white().mate(), pv=[m.uci() for m in i.get('pv',[])])
            for i in rows]
    return dict(root=analyze(multipv=3),
        played=analyze(root_moves=[chess.Move.from_uci(case['played'])]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pgn', default='research/data/user_games_v094.pgn')
    p.add_argument('--engine')
    p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--nodes', type=int)
    p.add_argument('--profile', choices=['tactical','full','conservative'], default='tactical')
    p.add_argument('--stockfish')
    p.add_argument('--reference-seconds', type=float, default=2)
    p.add_argument('--replay-only', action='store_true')
    p.add_argument('--trace-limit', type=int, default=0)
    p.add_argument('--output', required=True)
    args=p.parse_args()
    if args.engine:
        sys.path.insert(0, str(Path(args.engine).resolve()))
    games,cases=replay(args.pgn)
    report=dict(games=games,cases=cases,runs=[],python=sys.version,platform=platform.platform(),
        engine=args.engine,seconds=args.seconds,nodes=args.nodes,profile=args.profile,
        pgn_sha256=hashlib.sha256(Path(args.pgn).read_bytes()).hexdigest(),
        scope='Fresh TT per position, replayed history, no UI depth cap; fixed full-time budget.')
    dest=Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    def save(): dest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    save()
    if args.replay_only: return
    if args.stockfish:
        with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
            engine.configure({'Threads':1,'Hash':32})
            report['reference_engine']=engine.id
            for case in cases:
                report['runs'].append(dict(id=case['id'],reference=reference(
                    engine,case,args.reference_seconds,args.nodes)))
                save(); print(case['id'],flush=True)
    else:
        for case in cases:
            if case['kind']=='passed': continue
            report['runs'].append(dict(id=case['id'],tal=tal(case,args.seconds,args.nodes,
                args.profile,args.trace_limit)))
            save(); print(case['id'],report['runs'][-1]['tal']['move'],flush=True)


if __name__=='__main__': main()
