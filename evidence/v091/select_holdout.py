import csv
import hashlib
import json
import subprocess
from pathlib import Path
import chess

old = set()
paths = [*Path('evidence-v087').glob('*.json'), *Path('evidence-v089').glob('*lichess*.json'),
         Path('evidence-v089/fresh-suite.json'), Path('evidence-speed089/fixed-suite.json')]
def collect(value):
    if isinstance(value, dict):
        game = value.get('game')
        if isinstance(game, str):
            old.add(game)
        for item in value.values():
            collect(item)
    elif isinstance(value, list):
        for item in value:
            collect(item)
for p in paths:
    collect(json.loads(p.read_text()))
selected = {}
with subprocess.Popen(['zstd','-dc','evidence-v087/lichess_db_puzzle.csv.zst'], stdout=subprocess.PIPE,
                      text=True, encoding='utf-8') as process:
    for row in csv.DictReader(process.stdout):
        if int(row['Popularity']) < 92 or int(row['NbPlays']) < 400 or not 1500 <= int(row['Rating']) <= 2350:
            continue
        path = row['GameUrl'].split('#', 1)[0].split('/')[3:]
        game = path[1] if path[0] == 'game' else path[0]
        if game in old:
            continue
        themes = set(row['Themes'].split())
        if 'sacrifice' in themes and themes & {'long','veryLong'} and 'mate' not in themes:
            category = 'long_sacrifice'
        elif themes & {'mateIn3','mateIn4','mateIn5'}:
            category = 'forced_mate'
        elif 'defensiveMove' in themes:
            category = 'defense'
        elif 'short' in themes and 'mate' not in themes:
            category = 'short'
        else:
            continue
        tag = hashlib.sha256(f"tal091-blind:{row['PuzzleId']}".encode()).hexdigest()
        bucket = selected.setdefault(category, {})
        if len(bucket) >= 12 and tag >= max(v[0] for v in bucket.values()):
            continue
        if game not in bucket or tag < bucket[game][0]:
            bucket[game] = (tag, row)
        if len(bucket) > 12:
            del bucket[max(bucket, key=lambda g: bucket[g][0])]
    if process.wait():
        raise SystemExit('CSV unavailable')
seen = set()
suite = []
for category, bucket in sorted(selected.items()):
    for game, (tag, row) in sorted(bucket.items(), key=lambda item: item[1][0]):
        if game in seen:
            continue
        board = chess.Board(row['FEN'])
        solution = row['Moves'].split()
        board.push_uci(solution[0])
        suite.append(dict(id='lichess_'+row['PuzzleId'], game=game, source=row['GameUrl'],
                          suite=category, fen=board.fen(en_passant='fen'), bm=[solution[1]],
                          rating=int(row['Rating']), solution=solution[1:]))
        seen.add(game)
        if sum(item['suite']==category for item in suite)==8:
            break
assert len(suite)==32, {key: len(value) for key, value in selected.items()}
Path('evidence-v091/holdout.json').write_text(json.dumps(suite,indent=2)+'\n')
