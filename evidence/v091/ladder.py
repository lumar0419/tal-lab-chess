import json, sys, time
from pathlib import Path
root, profile, seconds, position, output = sys.argv[1:]
sys.path.insert(0, root)
from board import Board
from search import Searcher
cases = json.loads(Path(__file__).with_name('development.json').read_text())
case = next(row for row in cases if row['id'] == position)
b = Board(case['fen'])
s = Searcher(tt_size=300000)
if profile == 'selective':
    s.selective = True
elif profile == 'conservative':
    s.lmr = True
elif profile == 'deep':
    from deep_analysis import make_searcher
    s = make_searcher()
start = time.monotonic()
with open(output, 'w', buffering=1) as out:
    def publish(info):
        data = dict(id=position, depth=info.depth, score=info.score, nodes=info.nodes,
                    seconds=info.seconds, pv=[m.uci() for m in info.pv])
        out.write(json.dumps(data)+'\n')
        print(position, info.depth, round(info.seconds,2), info.score, data['pv'][:4], flush=True)
    s.search(b, time_limit=float(seconds), full_time=True, on_info=publish)
    out.write(json.dumps(dict(elapsed=time.monotonic()-start,total_nodes=s.nodes))+'\n')
