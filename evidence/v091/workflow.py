import json, sys
from pathlib import Path
root, case_id, seconds, output = sys.argv[1:]
sys.path.insert(0,root)
from board import Board
from deep_analysis import analyze_deep
suite=json.loads(Path(__file__).with_name('development.json').read_text())
row=next(r for r in suite if r['id']==case_id)
b=Board(row['fen'])
with open(output,'w',buffering=1) as stream:
    def update(result):
        stream.seek(0)
        json.dump(result,stream,indent=2)
        stream.truncate()
    analyze_deep(b,float(seconds),on_progress=update)
