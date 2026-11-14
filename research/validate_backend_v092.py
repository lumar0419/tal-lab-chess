"""Independent legal-move/attack/hash/evaluation oracle, deterministic seed.

Run with Python and `python native_engine.py research.validate_backend_v092`.
Compare JSON digests. python-chess is a validation dependency only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

import chess
from board import Board, SQUARES, sq_name
from evaluate import evaluate_white, evaluate_white_terms


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--games',type=int,default=20)
    args=p.parse_args()
    rng=random.Random(9200419)
    digest=hashlib.sha256()
    count=edges=attacks=0
    start=time.perf_counter()
    for game in range(args.games):
        ref=chess.Board();b=Board()
        for ply in range(100):
            moves=b.legal_moves()
            tokens=sorted(m.uci() for m in moves)
            assert tokens==sorted(m.uci() for m in ref.legal_moves),(game,ply,b.fen())
            assert b.hash==b.compute_hash()
            assert evaluate_white(b)==evaluate_white_terms(b)
            before=b.snapshot()
            for m in moves:
                b.make_move(m)
                assert b.hash==b.compute_hash(),m
                b.unmake_move()
                assert before==b.snapshot(),m
                edges+=1
            for s in SQUARES:
                for side in (0,1):
                    assert b.is_attacked(s,side)==ref.is_attacked_by(side==0,chess.parse_square(sq_name(s)))
                    attacks+=1
            digest.update(json.dumps([b.fen(),tokens,b.hash,evaluate_white(b)]).encode())
            count+=1
            if not moves or ref.is_game_over(): break
            token=rng.choice(tokens)
            b.push_uci(token);ref.push_uci(token)
    import board
    result=dict(backend=board.__file__,games=args.games,positions=count,edges=edges,
                attack_comparisons=attacks,digest=digest.hexdigest(),seconds=time.perf_counter()-start)
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
