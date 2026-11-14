"""External Stockfish reference only. Never imported by the Tal Lab engine."""
import argparse
import json
from pathlib import Path

import chess
import chess.engine


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',required=True)
    p.add_argument('--stockfish',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--seconds',type=float,default=1)
    args=p.parse_args()
    result={'seconds':args.seconds,'threads':1,'hash_mb':32,'rows':[]}
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        engine.configure({'Threads':1,'Hash':32})
        result['engine']=engine.id
        for case in json.loads(Path(args.suite).read_text()):
            b=chess.Board(case['fen'])
            def serialize(lines):
                return [dict(depth=i.get('depth'),nodes=i.get('nodes'),
                    score=i['score'].white().score(mate_score=30000),
                    mate=i['score'].white().mate(),pv=[m.uci() for m in i['pv']]) for i in lines]
            engine.configure({'Clear Hash':None})
            root=serialize(engine.analyse(b,chess.engine.Limit(time=args.seconds),multipv=3))
            chosen=case.get('bm',[case.get('historical_uci')])[0]
            b.push_uci(chosen)
            engine.configure({'Clear Hash':None})
            defense=serialize(engine.analyse(b,chess.engine.Limit(time=args.seconds),multipv=2)) if not b.is_game_over() else []
            result['rows'].append(dict(id=case['id'],expected=chosen,root=root,defense=defense))
            Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
            print(case['id'],root[0]['pv'][0],root[0]['score'],flush=True)


if __name__=='__main__':
    main()
