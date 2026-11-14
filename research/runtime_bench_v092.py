"""Same-process warm/cold CPython/PyPy/Cython measurements of identical code.

No python-chess dependency. Run one runtime at a time on the same pinned CPU.
"""
import argparse
import json
from pathlib import Path
import platform
import sys
import time

from board import Board
import board
import evaluate
from search import Searcher


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--depth',type=int,default=5)
    p.add_argument('--warmups',type=int,default=2)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--seconds',type=float)
    args=p.parse_args()
    cases=json.loads(Path('evidence/v091/historical.json').read_text())
    names=['kasparov_topalov_1999_ply47','rotlewi_rubinstein_1907_ply44',
           'lasker_bauer_1889_ply29','lasker_bauer_1889_ply33']
    # Archive IDs remain explicit in the output if spelling differs.
    selected=[c for c in cases if c['id'] in names]
    if len(selected)!=4:
        selected=[c for c in cases if c['historical_san'] in ('Rxd4','Rxc3','Bxh7+','Bxg7')]
    if len(selected)!=4:
        raise ValueError('Expected exactly four historical diagnostic cases')
    result=dict(runtime=platform.python_implementation(),version=sys.version,
        backend=board.__file__,platform=platform.platform(),warmups=args.warmups,
        repeats=args.repeats,depth=args.depth,seconds=args.seconds,runs=[])
    for repeat in range(-args.warmups,args.repeats):
        for c in selected:
            engine=Searcher(tt_size=300000);engine.lmr=True
            evaluate.clear_pawn_cache()
            b=Board(c['fen']);before=b.snapshot();rows=[]
            start=time.perf_counter()
            move,score=engine.search(b,max_depth=args.depth if args.seconds is None else 64,
                time_limit=args.seconds,full_time=True,on_info=lambda i:rows.append(dict(
                    depth=i.depth,score=i.score,nodes=i.nodes,seconds=i.seconds,pv=[m.uci() for m in i.pv])))
            elapsed=time.perf_counter()-start
            assert b.snapshot()==before
            result['runs'].append(dict(id=c['id'],repeat=repeat,warmup=repeat<0,rows=rows,
                historical=c['historical_uci'],move=move.uci(),score=score,nodes=engine.nodes,
                elapsed=elapsed,nps=engine.nodes/elapsed))
            Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
            print(c['id'],repeat,round(elapsed,3),rows[-1]['depth'],move.uci(),flush=True)
    try:
        import resource
        result['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        result['max_rss_kib']=None
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
