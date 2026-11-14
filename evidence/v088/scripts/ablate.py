import sys, json, time
sys.path.insert(0, sys.argv[1])
from board import Board
from search import Searcher
suite = {c['id']: c for c in json.load(open('/home/claude/v087/res/suite.json'))}
depth = int(sys.argv[2])
flags = ['sel_qsearch', 'sel_null', 'sel_rfp', 'sel_futility', 'sel_lmr', 'sel_iir', 'sel_order']
for cid in sys.argv[3:]:
    c = suite[cid]; print(cid, c['san'], c['fen'])
    for off in [None] + flags:
        s = Searcher(); s.selective = True
        if off: setattr(s, off, False)
        rows = []
        s.search(Board(c['fen']), max_depth=depth, on_info=lambda i: rows.append(f"{i.depth}:{i.pv[0].uci()}{'*' if i.pv[0].uci() in c['bm'] else ''}({i.score})"))
        print(f"  -{off or 'none':13s} nodes {s.nodes:>8,}  " + ' '.join(rows[2:]))
