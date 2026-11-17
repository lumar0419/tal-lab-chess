"""Research-only UCI wrapper; never a production entry point."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
from research.positional_v094 import candidate, group_weights
from search import Searcher
import uci


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation',choices=['baseline','mobility','king','development','combined','tuned'],default='baseline')
    p.add_argument('--fit',default='evidence/v094/texel-fit.json')
    p.add_argument('--no-quiet-pruning',action='store_true')
    args=p.parse_args()
    if args.no_quiet_pruning:
        original=Searcher.__init__
        def init(self,*a,**kw):
            original(self,*a,**kw);self.sel_futility=False
        Searcher.__init__=init
    weights=json.loads(Path(args.fit).read_text())['weights'] if args.evaluation=='tuned' else (
        group_weights(args.evaluation) if args.evaluation!='baseline' else None)
    with candidate(weights) if weights is not None and any(weights) else nullcontext():
        uci.main()


if __name__=='__main__': main()
