import json,sys
from pathlib import Path
sys.path.insert(0,str(Path('tal-v091').resolve()))
from board import Board
from search import Searcher
from deep_analysis import make_searcher
source=next(r for r in json.loads(Path(__file__).with_name('historical.json').read_text())
            if r['id']=='lasker_bauer_1889_ply33')
runs=[]
for profile in ('full','conservative'):
    for move in (None,'e5g7','h5g4'):
        report=[]
        engine=make_searcher(profile)
        engine.search(Board(source['fen']),max_depth=6,root_moves=[move] if move else None,
                      on_info=lambda i: report.append(dict(depth=i.depth,score=i.score,nodes=i.nodes,
                                             pv=[m.uci() for m in i.pv],seconds=i.seconds)))
        runs.append(dict(profile=profile,move=move,rows=report))
        print(profile,move,report[-1],flush=True)
Path('evidence-v091/diagnostic-bxg7-fixed.json').write_text(json.dumps(runs,indent=2)+'\n')
