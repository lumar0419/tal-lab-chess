import json, sys
from pathlib import Path
import chess
import chess.engine
source, output = sys.argv[1:]
cases=json.loads(Path(source).read_text())
engine_file=str(Path('reference-engine/stockfish/stockfish-ubuntu-x86-64-avx2').resolve())
with chess.engine.SimpleEngine.popen_uci(engine_file) as engine, open(output,'w',buffering=1) as out:
    engine.configure({'Threads': 1, 'Hash': 32})
    for row in cases:
        board=chess.Board(row['fen'])
        chosen=row['bm'][0]
        def serialize(lines):
            return [dict(move=q['pv'][0].uci(),pv=[m.uci() for m in q['pv']], depth=q['depth'],
                         cp=q['score'].white().score(),mate=q['score'].white().mate(),nodes=q.get('nodes')) for q in lines]
        lines=engine.analyse(board,chess.engine.Limit(time=2),multipv=3)
        after=None
        if row['suite']=='historical':
            board.push_uci(chosen)
            after=serialize(engine.analyse(board,chess.engine.Limit(time=2),multipv=3))
        out.write(json.dumps(dict(id=row['id'], expected=chosen, root=serialize(lines), defense=after))+'\n')
