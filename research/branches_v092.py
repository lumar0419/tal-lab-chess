"""Explicit accepted/declined historical branches; never a discovery score."""
import argparse
import json
from pathlib import Path
import platform
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source')
    p.add_argument('--output',required=True)
    p.add_argument('--seconds',type=float,default=20)
    args=p.parse_args()
    if args.source:sys.path.insert(0,str(Path(args.source).resolve()))
    from board import Board
    from search import Searcher
    cases={c['id']:c for c in json.loads(Path('evidence/v091/historical.json').read_text())}
    branches=[('kasparov_topalov_1999_ply47',['d1d4','c5d4']),
              ('kasparov_topalov_1999_ply47',['d1d4','a7b6']),
              ('kasparov_topalov_1999_ply47',['d1d4','a8d5']),
              ('rotlewi_rubinstein_1907_ply44',['c8c3','g3h4']),
              ('rotlewi_rubinstein_1907_ply44',['c8c3','e4b7']),
              ('lasker_bauer_1889_ply33',['e5g7','g8g7','h5g4','g7h7'])]
    report=dict(runtime=platform.python_implementation(),seconds=args.seconds,rows=[])
    for name,prefix in branches:
        b=Board(cases[name]['fen'])
        for token in prefix:b.push_uci(token)
        s=Searcher(tt_size=300000);s.lmr=True;rows=[]
        m,score=s.search(b,max_depth=16,time_limit=args.seconds,full_time=True,
            on_info=lambda i:rows.append(dict(depth=i.depth,score_white=i.score if b.side==0 else -i.score,
                nodes=i.nodes,seconds=i.seconds,pv=[m.uci() for m in i.pv])))
        report['rows'].append(dict(case=name,prefix=prefix,fen=b.fen(),iterations=rows))
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
        print(name,prefix,rows[-1],flush=True)
    controls=json.loads(Path('evidence/v091/control-cases.json').read_text())['rows']
    from deep_analysis import analyze_deep
    report['false_offers']=[]
    for row in controls:
        c=row['case']
        if 'forbidden' not in c:continue
        r=analyze_deep(Board(c['fen']),4,max_depth=5,candidate=c['forbidden'])
        item=next(x for x in r['candidates'] if x['move']==c['forbidden'])
        report['false_offers'].append(dict(case=c,root=r['root_move'],candidate=item,
                                          chose_forbidden=r['root_move']==c['forbidden']))
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
