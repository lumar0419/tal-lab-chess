import sys, time, json
sys.path.insert(0, sys.argv[1])
from board import Board
import search
from search import Searcher
fen = sys.argv[2]; depth = int(sys.argv[3]); opts = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
s = Searcher()
for k, v in opts.items(): setattr(s, k, v)
q = [0]
orig = Searcher.quiesce
def qz(self, *a, **k):
    q[0] += 1
    return orig(self, *a, **k)
Searcher.quiesce = qz
rows = []
t = time.perf_counter()
mv, sc = s.search(Board(fen), max_depth=depth, on_info=lambda i: rows.append((i.depth, i.score, i.nodes, round(time.perf_counter()-t, 2), i.pv[0].uci())))
for r in rows: print(r)
print('total', s.nodes, 'qsearch', q[0], f'({q[0]/s.nodes:.0%})', 'time', round(time.perf_counter()-t, 2))
