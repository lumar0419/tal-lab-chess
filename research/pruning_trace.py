"""Bounded, opt-in pruning log, plus fresh-TT forced branch comparisons.

python -m research.pruning_trace --fen FEN --seconds 5 --output trace.json
python -m research.pruning_trace --replay trace.json --index 0 --output replay.json

Replay compares a selected branch with full search at the same nominal depth.
It is a counterfactual experiment, not a reconstruction of the old TT/window.
"""
import argparse
import json
from pathlib import Path
import time

from board import Board
from search import INF, Searcher, TimeUp


class PruningTrace:
    def __init__(self, searcher, limit=1000):
        self.searcher = searcher
        self.limit = limit
        self.events = []
        self.dropped = 0

    def record(self, event, board, ply, depth, move, **details):
        if len(self.events) >= self.limit:
            self.dropped += 1
            return
        parent = Board(board.fen())
        parent.restore(board.snapshot())
        if details.get('after_move'):
            parent.unmake_move()
        self.events.append(dict(reason=event, fen=parent.fen(), ply=ply, depth=depth,
            move=move.uci() if move else None,
            history=[h[0].uci() for h in parent.history],
            gain=self.searcher._gain[ply], root_len=self.searcher.root_len,
            nodes=self.searcher.nodes, **details))


def counterfactual(event, seconds=10):
    result = {'event':event, 'scope':'Fresh TT, full window, forced root branch; original search context is not reproduced.',
              'runs':{}}
    for mode in ('selective','full'):
        board = Board(event['fen'])
        engine = Searcher(tt_size=300000)
        engine.selective = mode=='selective'
        rows=[]
        if event['depth'] == 0:
            # A selected capture must actually be played before comparing QS.
            original = board.snapshot()
            if event['move']:
                board.push_uci(event['move'])
            engine.start = time.monotonic()
            engine.deadline = engine.start+seconds
            try:
                score = engine.quiesce(board,-INF,INF,0)
                score = -score if event['move'] else score
                result['runs'][mode] = dict(score=score, nodes=engine.nodes, depth=0)
            except TimeUp:
                result['runs'][mode] = dict(status='incomplete',score=None,nodes=engine.nodes,depth=0)
            finally:
                board.restore(original)
        else:
            move,score=engine.search(board,max_depth=event['depth'],time_limit=seconds,
                root_moves=[event['move']] if event['move'] else None, full_time=True,
                on_info=lambda i: rows.append(dict(depth=i.depth,score=i.score,pv=[m.uci() for m in i.pv])))
            result['runs'][mode] = dict(score=score,move=move.uci() if move else None,
                nodes=engine.nodes, iterations=rows, completed_depth=rows[-1]['depth'] if rows else 0)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fen')
    p.add_argument('--seconds',type=float,default=5)
    p.add_argument('--output',required=True)
    p.add_argument('--replay')
    p.add_argument('--index',type=int,default=0)
    args=p.parse_args()
    if args.replay:
        report=counterfactual(json.loads(Path(args.replay).read_text())['events'][args.index],args.seconds)
    else:
        engine=Searcher()
        engine.selective=True
        trace=PruningTrace(engine)
        engine.selective_trace=trace
        engine.search(Board(args.fen),time_limit=args.seconds,full_time=True,on_info=None)
        report=dict(events=trace.events,dropped=trace.dropped,statistics=dict(engine.sel_stats))
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
