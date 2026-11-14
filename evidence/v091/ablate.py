import json,sys,time
from pathlib import Path
root, profile, setting, output=sys.argv[1:]
sys.path.insert(0,root)
from board import Board
from search import Searcher
cases=json.loads(Path(__file__).with_name('development.json').read_text())
cases=[r for r in cases if r['suite'] in ('ecm','iq4') or r['id'] in (
    'kasparov_topalov_1999_ply47','rotlewi_rubinstein_1907_ply44','lasker_bauer_1889_ply29','lasker_bauer_1889_ply33')]
with open(output,'w',buffering=1) as stream:
    for row in cases:
        b=Board(row['fen']); s=Searcher()
        s.selective=profile=='selective'
        s.lmr=profile=='conservative'
        if setting!='-':
            setattr(s,setting,False)
        samples=[]
        s.search(b,time_limit=3,full_time=True,on_info=lambda x:samples.append(
            dict(depth=x.depth,score=x.score,nodes=x.nodes,seconds=x.seconds,pv=[m.uci() for m in x.pv])))
        last=samples[-1]
        stream.write(json.dumps(dict(id=row['id'],expected=row['bm'],ok=last['pv'][0] in row['bm'],
                                     rows=samples,pruning=dict(s.sel_stats),nodes=s.nodes))+'\n')
