"""One-off option parity diagnostic; use --reference for v0.5.1 evaluate.py."""
import argparse
import importlib.util
import json
from pathlib import Path
import evaluate, search
from board import Board

def load(path):
    spec=importlib.util.spec_from_file_location('eval_old_reference',str(path))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--reference',required=True)
    ap.add_argument('--depth',type=int,default=3)
    args=ap.parse_args()
    previous=load(args.reference)
    data=json.loads((Path(__file__).parent/'tal_positions.json').read_text())['positions']
    featured=[p for p in data if p['featured']]
    for m in (previous,evaluate):
        m.ATTACK_ACTIVITY=True
        m.INITIATIVE=True
        m.KING_SAFETY=False
    old_fn=search.evaluate
    try:
        for p in featured:
            answers=[]
            for label, fn in (('v051',previous.evaluate),('v052',evaluate.evaluate)):
                search.evaluate=fn
                b=Board(p['fen'])
                s=search.Searcher(tt_size=3000)
                s.qsearch_quiet_checks=True
                s.tactical_ordering=True
                out=s.search(b,max_depth=args.depth)
                answers.append((out[0].uci() if out[0] else None,out[1]))
            print(f"{p['id']} {answers[0]} {answers[1]} {'SAME' if answers[0]==answers[1] else 'DIFFERENT'}")
    finally:
        search.evaluate=old_fn

if __name__=='__main__':main()
