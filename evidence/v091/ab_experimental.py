import json, sys, time
from pathlib import Path
root, profile, output = sys.argv[1:]
sys.path.insert(0, root)
import evaluate
from board import Board
from deep_analysis import make_searcher
from search import Searcher
target = {'kasparov_topalov_1999_ply47','rotlewi_rubinstein_1907_ply44','lasker_bauer_1889_ply29','lasker_bauer_1889_ply33'}
cases=[r for r in json.loads(Path(__file__).with_name('historical.json').read_text()) if r['id'] in target]
with open(output,'w',buffering=1) as dest:
    for r in cases:
        board=Board(r['fen']); s=make_searcher()
        if profile=='king_safety':
            evaluate.KING_SAFETY=True
        elif profile=='forcing':
            s.qsearch_quiet_checks=True
            s.check_continuation=True
            s.qsearch_forcing_replies=2
        elif profile=='limited_selective':
            s.selective=True
            s.sel_rfp=s.sel_futility=s.sel_qsearch=s.sel_iir=False
        rows=[]
        s.search(board,time_limit=15,full_time=True,on_info=lambda i:rows.append(
            dict(depth=i.depth,score=i.score,pv=[m.uci() for m in i.pv],nodes=i.nodes,time=i.seconds)))
        dest.write(json.dumps(dict(id=r['id'],expected=r['bm'],rows=rows))+'\n')
