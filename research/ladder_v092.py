"""One 600s search, checkpointed at 60/180/300/600; all completed iterations.

Use --source for an archived engine, --native for optional compiled sources.
Intermediate checkpoints from one search are not separate budget trials.
"""
import argparse
import json
from pathlib import Path
import platform
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source')
    p.add_argument('--native',action='store_true')
    p.add_argument('--case',default='kasparov_topalov_1999_ply47')
    p.add_argument('--profile',choices=['full','conservative','selective'],default='conservative')
    p.add_argument('--seconds',type=float,default=600)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    cases=json.loads(Path('evidence/v091/historical.json').read_text())
    case=next(c for c in cases if c['id']==args.case)
    if args.source:
        sys.path.insert(0,str(Path(args.source).resolve()))
    elif args.native:
        from native_engine import activate
        activate()
    from board import Board
    import board
    from search import Searcher
    b=Board(case['fen']);before=b.snapshot();s=Searcher(tt_size=300000)
    s.lmr=args.profile=='conservative';s.selective=args.profile=='selective'
    result=dict(case=case['id'],fen=case['fen'],historical=case['historical_uci'],
        python=sys.version,runtime=platform.python_implementation(),backend=board.__file__,
        profile=args.profile,seconds=args.seconds,rows=[],checkpoints={})
    out=Path(args.output)
    def collect(i):
        result['rows'].append(dict(depth=i.depth,score=i.score,nodes=i.nodes,seconds=i.seconds,
            nps=i.nodes/i.seconds,pv=[m.uci() for m in i.pv]))
        out.write_text(json.dumps(result,indent=2)+'\n')
        print(case['id'],i.depth,round(i.seconds,2),i.score,result['rows'][-1]['pv'][:6],flush=True)
    start=time.perf_counter()
    move,score=s.search(b,max_depth=64,time_limit=args.seconds,full_time=True,on_info=collect)
    result.update(elapsed=time.perf_counter()-start,nodes=s.nodes,move=move.uci(),score=score)
    for seconds in (60,180,300,600):
        if seconds<=args.seconds:
            result['checkpoints'][str(seconds)]=next((r for r in reversed(result['rows']) if r['seconds']<=seconds),None)
    assert before==b.snapshot()
    out.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
