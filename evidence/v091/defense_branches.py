import json, sys
from pathlib import Path
sys.path.insert(0,str(Path('tal-v091').resolve()))
from board import Board, WHITE
from deep_analysis import make_searcher

which, outpath = sys.argv[1:]
ids = {'rxd4':'kasparov_topalov_1999_ply47','rxc3':'rotlewi_rubinstein_1907_ply44'}
replies = {'rxd4':['c5d4','a7b6','a8d5'], 'rxc3':['g3h4','e4b7','f1f3']}
r=next(r for r in json.loads(Path(__file__).with_name('historical.json').read_text()) if r['id']==ids[which])
b=Board(r['fen'])
b.push_uci(r['bm'][0])
with open(outpath,'w',buffering=1) as out:
    for reply in replies[which]:
        samples=[]
        engine=make_searcher()
        engine.search(b,root_moves=[reply],time_limit=25,full_time=True,on_info=lambda i:samples.append(
            dict(depth=i.depth,score=i.score if b.side==WHITE else -i.score,nodes=i.nodes,
                 time=i.seconds,pv=[m.uci() for m in i.pv])))
        out.write(json.dumps(dict(id=r['id'],root=r['bm'][0],reply=reply,iterations=samples))+'\n')
