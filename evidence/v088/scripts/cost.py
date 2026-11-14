import sys, json, time
sys.path.insert(0, sys.argv[1])
from board import Board; from search import Searcher
suite = json.load(open('/home/claude/v087/res/suite.json'))
depth = int(sys.argv[2]); cfgs = [json.loads(a) for a in sys.argv[3:]]
import random
cases = random.Random(1).sample([c for c in suite if c['suite'] == 'wac'], 24) + [{'id':'kasp','fen':'b2r3r/k4p1p/p2q1np1/NppP4/3p1Q2/P4PPB/1PP4P/1K1RR3 w - - 1 24','bm':['d1d4']}]
for cfg in cfgs:
    tot = 0; ok = 0; t = time.perf_counter(); fd = 0
    for c in cases:
        s = Searcher()
        for k, v in cfg.items(): setattr(s, k, v)
        first = [None]
        def info(i, first=first):
            if i.pv and i.pv[0].uci() in c['bm']:
                if first[0] is None: first[0] = i.depth
            else: first[0] = None
        mv, sc = s.search(Board(c['fen']), max_depth=depth, on_info=info)
        tot += s.nodes; ok += mv.uci() in c['bm']; fd += first[0] or (depth + 2)
    print(f"{json.dumps(cfg):70s} nodes {tot:>10,} solved {ok}/{len(cases)} 발견깊이합 {fd} {time.perf_counter()-t:.1f}s", flush=True)
