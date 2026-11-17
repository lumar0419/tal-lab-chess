"""Game-grouped Texel experiment; never installs fitted weights in the engine.

prepare: stream a licensed PGN or .pgn.zst, split whole games, discard duplicate
positions globally and exclude known diagnostic/test FENs. Fit K on training
only, coordinate-fit bounded integer weights on training, choose by validation,
then evaluate the locked test split once. Result MSE is NOT playing strength.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform

import chess
import chess.pgn

from board import Board
import evaluate
from research.positional_v094 import features, NAMES, INITIAL


def key(fen):
    return ' '.join(chess.Board(fen).fen(en_passant='legal').split()[:4])


def split_game(game_id, seed):
    bucket=int(hashlib.sha256(f'{seed}:{game_id}'.encode()).hexdigest()[:8],16)%100
    return 'train' if bucket<70 else 'validation' if bucket<85 else 'test'


def known_positions(paths):
    keys=set()
    def visit(obj):
        if isinstance(obj,dict):
            if isinstance(obj.get('fen'),str):
                try: keys.add(key(obj['fen']))
                except ValueError: pass
            for v in obj.values(): visit(v)
        elif isinstance(obj,list):
            for v in obj: visit(v)
    for path in paths:
        try: visit(json.loads(Path(path).read_text()))
        except (ValueError,UnicodeError): pass
    return keys


def prepare(args):
    import zstandard
    # Freeze the exclusion universe: including this experiment's own output
    # would exclude its test samples on a rerun and silently change the data.
    excluded=known_positions(p for version in ('v090','v091','v092','v093')
                             for p in (Path('evidence')/version).glob('*.json'))
    # Include every played position, not only the requested diagnostic moves.
    from research.diagnostics_v094 import replay
    games,cases=replay('research/data/user_games_v094.pgn')
    excluded.update(key(p['fen']) for g in games for p in g['positions'])
    seen=set(); seen_games=set(); rows=[]; counts={}; rejected={}; processed=0
    source=Path(args.input)
    with source.open('rb') as raw:
        stream=zstandard.ZstdDecompressor().stream_reader(raw) if source.suffix=='.zst' else raw
        with io.TextIOWrapper(stream,encoding='utf-8') as text:
            while processed<args.games and (game:=chess.pgn.read_game(text)) is not None:
                processed+=1
                result={'1-0':1.,'0-1':0.,'1/2-1/2':.5}.get(game.headers.get('Result'))
                if game.errors or result is None: continue
                # Move sequence digest prevents re-exported duplicate games
                # with different Site identifiers from crossing partitions.
                moves=list(game.mainline_moves())
                gid=hashlib.sha256((game.board().fen()+' '+' '.join(m.uci() for m in moves)).encode()).hexdigest()
                if gid in seen_games: continue
                seen_games.add(gid)
                split=split_game(gid,args.seed)
                board=game.board()
                for ply,move in enumerate(moves,1):
                    capture=board.is_capture(move)
                    board.push(move)
                    if ply<16 or ply%8 or capture or move.promotion or board.is_check() or board.is_game_over(): continue
                    # Reject immediately unstable material: this is a static
                    # evaluator fit, not training on unsearched hanging pieces.
                    if any(board.is_capture(m) for m in board.legal_moves): continue
                    fen=board.fen(); k=key(fen)
                    if k in seen or k in excluded:
                        rejected['duplicate_or_excluded']=rejected.get('duplicate_or_excluded',0)+1
                        continue
                    seen.add(k)
                    b=Board(fen); terms,phase,dead=evaluate.eval_terms(b)
                    if dead: continue
                    base=sum(mg*phase+eg*(24-phase) for mg,eg in terms.values())/24
                    rows.append(dict(fen=fen,game=gid,split=split,result=result,
                        base=base,features=features(b)))
                    counts[split]=counts.get(split,0)+1
                if processed%1000==0: print('games',processed,'positions',len(rows),flush=True)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    report=dict(source=args.source,license='CC0-1.0 (Lichess database)',
        source_sha256=digest,seed=args.seed,games_read=processed,unique_games=len(seen_games),
        counts=counts,rejected=rejected,exclusion_positions=len(excluded),
        policy='Game move-sequence hash split 70/15/15; global first-occurrence position dedup; quiet nonterminal positions every 8 plies from ply 16.',rows=rows)
    Path(args.output).write_text(json.dumps(report,separators=(',',':'))+'\n')


def fit(args):
    import numpy as np
    raw=Path(args.input).read_bytes()
    data=json.loads(gzip.decompress(raw) if args.input.endswith('.gz') else raw); rows=data['rows']
    games={}; positions={}; partitions={}
    for r in rows:
        if r['split'] not in ('train','validation','test'): raise ValueError('invalid split')
        if r['game'] in games and games[r['game']]!=r['split']: raise ValueError('game leakage')
        games[r['game']]=r['split']
        k=key(r['fen'])
        if k in positions: raise ValueError('duplicate position')
        positions[k]=r['split']
    for split in ('train','validation','test'):
        rs=[r for r in rows if r['split']==split]
        if len(rs)<100: raise ValueError(f'insufficient {split} positions: {len(rs)}')
        partitions[split]=(np.array([r['base'] for r in rs]),
            np.array([r['features'] for r in rs],dtype=float)/24,
            np.array([r['result'] for r in rs]))
    def loss(split, weights, k):
        b,x,y=partitions[split]
        score=b+x@weights
        probability=1/(1+np.power(10.,np.clip(-k*score/400.,-20,20)))
        return float(np.mean((y-probability)**2))
    zero=np.zeros(len(NAMES),dtype=int)
    k=min((i/20 for i in range(5,61)),key=lambda k:loss('train',zero,k))
    weights=zero.copy(); best=zero.copy(); best_val=loss('validation',best,k); log=[]
    # Training-only coordinate descent; validation chooses a saved pass,
    # not individual coordinates. No test evaluation inside selection.
    for step in (8,4,2,1):
        for iteration in range(8):
            changed=False
            for i in range(len(weights)):
                old=weights[i]; best_loss=loss('train',weights,k); value=old
                for proposed in (old-step,old+step):
                    if not 0<=proposed<=48: continue
                    trial=weights.copy();trial[i]=proposed
                    trial_loss=loss('train',trial,k)
                    if trial_loss<best_loss-1e-10: best_loss,value=trial_loss,proposed
                if value!=old: weights[i]=value;changed=True
            validation=loss('validation',weights,k)
            log.append(dict(step=step,iteration=iteration,train=loss('train',weights,k),validation=validation,weights=weights.tolist()))
            if validation<best_val: best,best_val=weights.copy(),validation
            if not changed: break
    report=dict(names=NAMES,weights=best.tolist(),k=k,input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        counts=data['counts'],source=data['source'],seed=data['seed'],python=platform.python_version(),
        baseline={s:loss(s,zero,k) for s in partitions},
        candidate={s:loss(s,best,k) for s in partitions},passes=log,
        status='research-only hypothesis; independent match acceptance required')
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print({k:v for k,v in report.items() if k!='passes'})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','fit']); p.add_argument('--input',required=True)
    p.add_argument('--output',required=True);p.add_argument('--games',type=int,default=10000)
    p.add_argument('--seed',type=int,default=9417)
    p.add_argument('--source',default='https://database.lichess.org/standard/lichess_db_standard_rated_2013-01.pgn.zst')
    args=p.parse_args(); (prepare if args.mode=='prepare' else fit)(args)


if __name__=='__main__': main()
