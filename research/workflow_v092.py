"""Historical deep-workflow comparison, with explicit diagnostic candidate.

Root rows always come from unrestricted general search. An explicitly supplied
historical move is included only in the later forced-candidate comparisons.
"""
import argparse
import json
from pathlib import Path
import platform
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source')
    p.add_argument('--case',required=True)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--fixed',action='store_true')
    p.add_argument('--output',required=True)
    args=p.parse_args()
    case=next(c for c in json.loads(Path('evidence/v091/historical.json').read_text()) if c['id']==args.case)
    if args.source:sys.path.insert(0,str(Path(args.source).resolve()))
    from board import Board
    import board
    from deep_analysis import analyze_deep
    result=dict(case=case,runtime=platform.python_implementation(),python=sys.version,backend=board.__file__)
    out=Path(args.output)
    last=[None]
    def publish(report):
        result['report']=report
        out.write_text(json.dumps(result,indent=2)+'\n')
        status=report['phase'],report['attempting']
        if last[0]!=status:
            print(status,report.get('root_move'),report['elapsed'],flush=True)
            last[0]=status
    options={} if args.source else dict(adaptive=not args.fixed)
    result['report']=analyze_deep(Board(case['fen']),args.seconds,profile='conservative',
        candidate=case['historical_uci'],on_progress=publish,**options)
    out.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
