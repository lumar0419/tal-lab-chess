import json, sys, time
root, profile, source, output, seconds, shard, shards = sys.argv[1:]
sys.path.insert(0, root)
from board import Board
from search import Searcher, mate_plies
from pathlib import Path

suite = json.loads(Path(source).read_text())[int(shard)::int(shards)]
with open(output,'w',buffering=1) as out:
    for case in suite:
        board = Board(case['fen'])
        engine = Searcher()
        if profile == 'full':
            pass
        elif profile == 'selective':
            engine.selective = True
        elif profile == 'conservative_base':
            engine.lmr = True
        else:
            from deep_analysis import make_searcher
            engine = make_searcher(profile)
        rows = []
        def completed(info):
            rows.append(dict(depth=info.depth, score=info.score, nodes=info.nodes,
                             seconds=round(info.seconds,4), pv=[move.uci() for move in info.pv]))
        start = time.monotonic()
        engine.search(board, time_limit=float(seconds), full_time=True, on_info=completed)
        last = rows[-1]
        expected = case['bm']
        plies = mate_plies(last['score'])
        proof = None
        if case['suite'] == 'forced_mate' and plies in (1,3,5,7) and last['score']>0:
            from sacrifice import mate_proof
            proof = mate_proof(board, last['pv'][0], plies, deadline=time.monotonic()+1)
        out.write(json.dumps(dict(id=case['id'],category=case['suite'], expected=expected,
                                  ok=last['pv'][0] in expected, move=last['pv'][0],
                                  depth=last['depth'], score=last['score'], mate_in_plies=plies,
                                  proof=proof,nodes=engine.nodes, elapsed=time.monotonic()-start,
                                  rows=rows))+'\n')
