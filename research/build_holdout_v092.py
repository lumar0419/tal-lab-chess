"""Freeze a new CC0 Lichess sample, excluding all archived JSON games/FENs.

No Tal Lab search is run by this script. Positional compensation is a proxy
category, not expert-verified positional ground truth. Serial sacrifices are
checked against the supplied solution with an independent exchange evaluator.
Requires python-chess, zstandard and network access. Stops after a bounded prefix.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.request

import chess
import zstandard
from research.epd_suite import see

URL='https://database.lichess.org/lichess_db_puzzle.csv.zst'
CATEGORIES=('short_mate','long_mate','sacrifice','serial_sacrifice',
            'positional_compensation_proxy','quiet_attack','defense','bad_sacrifice_refutation')


def archived(root):
    games=set();fens=set()
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if isinstance(v,str):
                    if k in ('game','game_id'): games.add(v)
                    if k=='fen': fens.add(' '.join(v.split()[:4]))
                    if 'lichess.org/' in v:
                        path=v.split('lichess.org/')[1].split('#')[0].split('/')
                        if path and path[0]=='game':path=path[1:]
                        if path:games.add(path[0])
                walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
    for p in root.rglob('*.json'):
        if 'v092' in p.parts or '.git' in p.parts or 'build' in p.parts:continue
        try: walk(json.loads(p.read_text()))
        except (ValueError,UnicodeError):pass
    return games,fens


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--per-category',type=int,default=4)
    p.add_argument('--max-rows',type=int,default=300000)
    args=p.parse_args()
    excluded_games,excluded_fens=archived(Path.cwd())
    used=set(excluded_games);cases=[];counts={k:0 for k in CATEGORIES}
    raw=[]
    request=urllib.request.Request(URL,headers={'User-Agent':'TalLab-validation/0.9.2'})
    with urllib.request.urlopen(request,timeout=90) as response:
        reader=zstandard.ZstdDecompressor().stream_reader(response)
        for index,row in enumerate(csv.DictReader(io.TextIOWrapper(reader,encoding='utf-8')),1):
            if index>args.max_rows or all(n>=args.per_category for n in counts.values()):break
            if not (1400<=int(row['Rating'])<=2600 and int(row['Popularity'])>=90 and int(row['NbPlays'])>=500):continue
            path=row['GameUrl'].split('lichess.org/')[-1].split('#')[0].split('/')
            if path[0]=='game':path=path[1:]
            game=path[0]
            if game in used:continue
            tags=set(row['Themes'].split());tokens=row['Moves'].split()
            before=chess.Board(row['FEN'])
            first=chess.Move.from_uci(tokens[0]);previous_piece=before.piece_type_at(first.from_square)
            previous_see=see(before,first)
            before.push(first)
            fen=before.fen(en_passant='fen')
            if ' '.join(fen.split()[:4]) in excluded_fens:continue
            answer=chess.Move.from_uci(tokens[1])
            candidate=None
            if 'mateIn1' in tags or 'mateIn2' in tags:candidate='short_mate'
            elif tags & {'mateIn4','mateIn5'}:candidate='long_mate'
            elif 'defensiveMove' in tags and 'sacrifice' not in tags:candidate='defense'
            elif (previous_piece in (chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT)
                  and previous_see<=-100 and answer.to_square==first.to_square
                  and 'mate' not in tags):candidate='bad_sacrifice_refutation'
            elif 'sacrifice' in tags and 'mate' not in tags:
                view=before.copy();negative=[];checks=[]
                for ply,token in enumerate(tokens[1:]):
                    m=chess.Move.from_uci(token)
                    if ply%2==0:
                        checks.append(view.gives_check(m))
                        if see(view,m)<=-100:negative.append(ply)
                    view.push(m)
                if len(negative)>=2:candidate='serial_sacrifice'
                elif ('veryLong' in tags and not any(checks[:2])
                      and not before.is_capture(answer)):candidate='positional_compensation_proxy'
                else:candidate='sacrifice'
            elif 'quietMove' in tags and 'mate' not in tags:candidate='quiet_attack'
            if candidate is None or counts[candidate]>=args.per_category:continue
            # Validate the entire source solution independently before freezing.
            view=before.copy()
            for token in tokens[1:]:view.push_uci(token)
            counts[candidate]+=1;used.add(game);raw.append(row)
            cases.append(dict(id='lichess_'+row['PuzzleId'],fen=fen,bm=[tokens[1]],
                solution=tokens[1:],category=candidate,themes=sorted(tags),game=game,
                rating=int(row['Rating']),source=row['GameUrl'],previous_see=previous_see))
            print(index,candidate,counts[candidate],flush=True)
    destination=Path(args.output)
    destination.write_text(json.dumps(cases,indent=2)+'\n')
    destination.with_suffix('.provenance.json').write_text(json.dumps(dict(
        url=URL,license='CC0',rows_examined=index,selection='First eligible rows in bounded source prefix; frozen before Tal Lab evaluation.',
        exclusion_games=len(excluded_games),exclusion_fens=len(excluded_fens),counts=counts,
        raw_rows_sha256=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),
        limitations=['Positional compensation is a non-forcing long-sacrifice proxy, not expert positional ground truth.',
                     'Puzzle themes and supplied solution are source labels; independent engine checks are separate.']),indent=2)+'\n')
    destination.with_suffix('.source.json').write_text(json.dumps(raw,indent=2)+'\n')


if __name__=='__main__':
    main()
