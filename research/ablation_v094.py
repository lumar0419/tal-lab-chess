"""Isolated positional/search ablations. Outputs raw, reproducible per-case data."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import platform
import time

from board import Board
from search import Searcher
from research.positional_v094 import candidate, group_weights


def run_case(case, variant, seconds, nodes, weights):
    engine=Searcher();engine.set_tactical(True)
    if variant=='F': engine.sel_futility=False  # hypothesis; research process only
    if variant=='conservative': engine.set_tactical(False);engine.lmr=True
    chosen=group_weights({'B':'mobility','C':'king','D':'development'}[variant]) if variant in 'BCD' else weights
    context=candidate(chosen) if variant in ('B','C','D','E','G') and any(chosen) else nullcontext()
    # G is only a candidate combination, never labelled validated by this tool.
    if variant=='G': engine.sel_futility=False
    board=Board() if 'moves' in case else Board(case['fen'])
    for move in case.get('moves',[]): board.push_uci(move)
    assert board.fen()==case['fen']
    before=board.snapshot();rows=[];multipv=case.get('multipv',1)
    def collect(i):
        rows.append(dict(depth=i.depth,score=i.score,nodes=i.nodes,
            seconds=i.seconds,pv=[m.uci() for m in i.pv]))
    started=time.perf_counter()
    with context:
        move,score=engine.search(board, node_limit=nodes,time_limit=None if nodes else seconds,
            full_time=True,multipv=multipv,on_info=collect if multipv==1 else None,
            on_multipv=(lambda group:collect(group[0])) if multipv>1 else None)
    elapsed=time.perf_counter()-started
    assert before==board.snapshot()
    return dict(id=case['id'],variant=variant,move=move.uci() if move else None,
        score_white=score*(1 if board.side==0 else -1),elapsed=elapsed,nodes=engine.nodes,
        nps=engine.nodes/elapsed,depth=rows[-1]['depth'] if rows else 0,
        pv=rows[-1]['pv'] if rows else [],correct=move.uci() in case['bm'] if case.get('bm') and move else None,
        statistics=dict(engine.sel_stats),iterations=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',required=True);p.add_argument('--output',required=True)
    p.add_argument('--seconds',type=float,default=2);p.add_argument('--nodes',type=int)
    p.add_argument('--variants',default='A,B,C,D,E,F,G,conservative')
    p.add_argument('--fit',default='evidence/v094/texel-fit.json')
    args=p.parse_args();cases=json.loads(Path(args.suite).read_text())
    weights=json.loads(Path(args.fit).read_text())['weights']
    report=dict(python=platform.python_version(),seconds=args.seconds,nodes=args.nodes,
        suite=args.suite,fit=args.fit,weights=weights,rows=[],
        note='E uses validation-selected weights. G is E + disabled quiet futility/LMP, not validated integration.')
    for index,case in enumerate(cases):
        variants=args.variants.split(',')
        # Rotate order to reduce systematic warmup/host-load bias.
        offset=index%len(variants);variants=variants[offset:]+variants[:offset]
        for variant in variants:
            row=run_case(case,variant,args.seconds,args.nodes,weights)
            report['rows'].append(row)
            Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
            print(case['id'],variant,row['move'],row['depth'],row['correct'],flush=True)


if __name__=='__main__': main()
