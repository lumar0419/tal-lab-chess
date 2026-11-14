import json
from pathlib import Path
from board import Board
from search import Searcher
case = next(r for r in json.loads(Path('../evidence-speed089/fixed-suite.json').read_text()) if r['id']=='kasparov_topalov_1999_ply47')
Searcher().search(Board(case['fen']), max_depth=5, full_time=True, on_info=None)
