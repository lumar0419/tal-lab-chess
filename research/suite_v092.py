"""Frozen-suite benchmark, fresh engine/TT per case, persistent runtime/JIT.

Source and native selection precede ALL engine imports. The source module is
shared by CPython and PyPy. Existing development suites stay labeled as such.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source')
    p.add_argument('--native',action='store_true')
    p.add_argument('--suite',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--seconds',type=float,default=3)
    p.add_argument('--defense-seconds',type=float,default=1)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--profile',choices=['full','conservative','selective'],default='conservative')
    args=p.parse_args()
    if args.source:
        sys.path.insert(0,str(Path(args.source).resolve()))
    elif args.native:
        from native_engine import activate
        activate()
    import board
    from board import Board
    from search import Searcher
    def engine():
        s=Searcher(tt_size=300000)
        s.lmr=args.profile=='conservative';s.selective=args.profile=='selective'
        return s
    # Same untimed warmup for every runtime, never using holdout positions.
    warm='b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24'
    for _ in range(2):engine().search(Board(warm),max_depth=5,on_info=None)
    raw=Path(args.suite).read_bytes();suite=json.loads(raw)
    result=dict(runtime=platform.python_implementation(),python=sys.version,backend=board.__file__,
        suite_sha256=hashlib.sha256(raw).hexdigest(),seconds=args.seconds,
        defense_seconds=args.defense_seconds,profile=args.profile,repeats=args.repeats,
        warmup='Two searches at depth 5 on the existing Kasparov development case',rows=[])
    out=Path(args.output)
    def run(b,seconds):
        s=engine();rows=[];original=b.snapshot();begin=time.perf_counter()
        move,score=s.search(b,max_depth=64,time_limit=seconds,full_time=True,
            on_info=lambda i:rows.append(dict(depth=i.depth,score=i.score,nodes=i.nodes,
                seconds=i.seconds,pv=[m.uci() for m in i.pv])))
        assert b.snapshot()==original
        return dict(move=move.uci() if move else None,score=score,rows=rows,
            completed_depth=rows[-1]['depth'] if rows else 0,nodes=s.nodes,
            elapsed=time.perf_counter()-begin)
    for repeat in range(args.repeats):
        # Reverse order on the second repetition to expose order/runtime drift.
        for case in (suite if repeat%2==0 else list(reversed(suite))):
            b=Board(case['fen'])
            data=run(b,args.seconds)
            bm=case.get('bm',[case.get('historical_uci')])
            data.update(id=case['id'],category=case.get('category',case.get('suite','historical')),
                        repeat=repeat,bm=bm,correct=data['move'] in bm)
            if args.defense_seconds>0 and bm[0]:
                b.push_uci(bm[0])
                if b.outcome() is None:
                    data['defense']=run(b,args.defense_seconds)
            result['rows'].append(data)
            out.write_text(json.dumps(result,indent=2)+'\n')
            print(case['id'],repeat,data['completed_depth'],data['move'],data['correct'],flush=True)
    try:
        import resource
        result['max_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        result['max_rss_kib']=None
    out.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
