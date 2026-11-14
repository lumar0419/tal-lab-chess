import json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tal-v091').resolve()))
from board import Board, WHITE
from deep_analysis import make_searcher
target,limit,outpath=sys.argv[1:]
r=next(row for row in json.loads(Path(__file__).with_name('historical.json').read_text()) if row['id']==target)
b=Board(r['fen'])
with open(outpath,'w',buffering=1) as stream:
    engine=make_searcher()
    def publish(i):
        stream.write(json.dumps(dict(depth=i.depth,score=i.score if b.side==WHITE else -i.score,
                                     seconds=i.seconds,nodes=i.nodes,pv=[m.uci() for m in i.pv]))+'\n')
    engine.search(b,time_limit=float(limit),full_time=True,on_info=publish)
    stream.write(json.dumps(dict(total_nodes=engine.nodes))+'\n')
