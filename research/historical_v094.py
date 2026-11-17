"""Historical sacrifice regressions with explicit budget and source checkout."""
import argparse
import json
from pathlib import Path
import platform
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source');p.add_argument('--nodes',type=int)
    p.add_argument('--seconds',type=float,default=60);p.add_argument('--output',required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if a.source:sys.path.insert(0,str(Path(a.source).resolve()))
    from board import Board
    from search import Searcher
    wanted={'kasparov_topalov_1999_ply47','rotlewi_rubinstein_1907_ply44',
            'lasker_bauer_1889_ply29','lasker_bauer_1889_ply33'}
    cases=[c for c in json.loads((root/'evidence/v091/historical.json').read_text()) if c['id'] in wanted]
    assert len(cases)==4
    report=dict(source=a.source or str(root),runtime=platform.python_implementation(),
        version=sys.version,nodes=a.nodes,seconds=None if a.nodes else a.seconds,rows=[])
    for c in cases:
        s=Searcher();s.set_tactical(True);b=Board(c['fen']);before=b.snapshot();rows=[]
        def collect(i):
            rows.append(dict(depth=i.depth,score=i.score,nodes=i.nodes,seconds=i.seconds,
                pv=[m.uci() for m in i.pv]))
        start=time.perf_counter()
        move,score=s.search(b,node_limit=a.nodes,time_limit=None if a.nodes else a.seconds,
            full_time=True,on_info=collect)
        assert before==b.snapshot()
        # Every PV must be playable, including rows that don't match history.
        for row in rows:
            view=Board(c['fen'])
            for token in row['pv']:
                assert view.parse_uci(token) is not None,(c['id'],row)
                view.push_uci(token)
        matches=[i for i in rows if i['pv'] and i['pv'][0]==c['historical_uci']]
        report['rows'].append(dict(id=c['id'],expected=c['historical_uci'],move=move.uci(),
            score=score,nodes=s.nodes,elapsed=time.perf_counter()-start,
            correct=move.uci()==c['historical_uci'],iterations=rows,
            first_seen_seconds=matches[0]['seconds'] if matches else None))
        Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
        print(c['id'],move.uci(),report['rows'][-1]['correct'],flush=True)


if __name__=='__main__':main()
