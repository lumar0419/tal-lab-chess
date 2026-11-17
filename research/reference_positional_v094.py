"""Reference the fresh positional set with a pinned, full-strength Stockfish.

Analyse each Tal candidate as a forced root, not by the engine's own score.
Separate bounded searches can disagree; negative measured loss is clamped to
zero and is never a claim the candidate beats the reference.
"""
import argparse
import json
from pathlib import Path
import time
import chess
import chess.engine


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',required=True);p.add_argument('--ablation')
    p.add_argument('--stockfish',required=True);p.add_argument('--output',required=True)
    p.add_argument('--seconds',type=float,default=2)
    args=p.parse_args();cases=json.loads(Path(args.suite).read_text())
    rows=json.loads(Path(args.ablation).read_text())['rows'] if args.ablation else []
    report=dict(engine=None,threads=1,hash_mb=32,seconds=args.seconds,rows=[])
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        engine.configure({'Threads':1,'Hash':32});report['engine']=engine.id
        for case in cases:
            b=chess.Board(case['fen'])
            def run(move=None):
                engine.configure({'Clear Hash':None});start=time.perf_counter()
                info=engine.analyse(b,chess.engine.Limit(time=args.seconds),
                    root_moves=[chess.Move.from_uci(move)] if move else None)
                return dict(depth=info['depth'],score_white=info['score'].white().score(mate_score=30000),
                    mate_white=info['score'].white().mate(),nodes=info['nodes'],nps=info.get('nps'),
                    elapsed=time.perf_counter()-start,pv=[m.uci() for m in info['pv']])
            root=run();moves=sorted({r['move'] for r in rows if r['id']==case['id'] and r['move']})
            forced={m:run(m) for m in moves}
            report['rows'].append(dict(id=case['id'],fen=case['fen'],root=root,forced=forced))
            Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
            print(case['id'],root['pv'][0],flush=True)


if __name__=='__main__':main()
