"""Run one JSON search task against the engine on PYTHONPATH."""
import json
import sys
import time

from board import Board
import evaluate
from search import Searcher


def main():
    task = json.load(sys.stdin)
    board = Board(task['fen'])
    for uci in task.get('history', []):
        board.push_uci(uci)
    if board.fen() != task.get('expected_fen', board.fen()):
        raise ValueError('Position does not match the replayed history')
    if task.get('after'):
        board.push_uci(task['after'])
    for uci in task.get('prefix', []):
        board.push_uci(uci)
    original = board.snapshot()
    evaluate.clear_pawn_cache()
    for flag, enabled in task.get('evaluation', {}).items():
        if flag not in ('ATTACK_ACTIVITY', 'INITIATIVE', 'KING_SAFETY') or type(enabled) is not bool:
            raise ValueError(f'Invalid evaluation option: {flag}')
        setattr(evaluate, flag, enabled)
    searcher = Searcher(tt_size=task.get('tt', 60000))
    for name, value in task.get('options', {}).items():
        if not hasattr(searcher, name):
            raise ValueError(f'Unknown search option: {name}')
        setattr(searcher, name, value)
    rows = []

    def collect(group):
        rows.append({
            'depth': group[0].depth,
            'nodes': max(line.nodes for line in group),
            'seconds': max(line.seconds for line in group),
            'lines': [{'move': line.pv[0].uci(), 'score': line.score,
                       'pv': [move.uci() for move in line.pv]} for line in group],
        })

    multipv = task.get('multipv', 1)
    begin = time.perf_counter()
    searcher.search(board, max_depth=task.get('depth', 14), time_limit=task.get('seconds'),
                    full_time=True, multipv=multipv, root_moves=task.get('roots'),
                    on_info=(lambda line: collect([line])) if multipv == 1 else None,
                    on_multipv=collect if multipv > 1 else None)
    elapsed = time.perf_counter() - begin
    if original != board.snapshot():
        raise RuntimeError('Search modified root board')
    print(json.dumps({
        'elapsed': elapsed, 'nodes': searcher.nodes, 'nps': searcher.nodes / elapsed,
        'rows': rows, 'lmr_probes': searcher.lmr_probes, 'lmr_researches': searcher.lmr_researches,
        'pvs_probes': searcher.pvs_probes, 'pvs_researches': searcher.pvs_researches, 'aspiration_probes': searcher.aspiration_probes,
        'aspiration_researches': searcher.aspiration_researches,
        'null_probes': getattr(searcher, 'null_probes', 0),
        'null_cutoffs': getattr(searcher, 'null_cutoffs', 0),
        'null_threats': getattr(searcher, 'null_threats', 0),
    }))


if __name__ == '__main__':
    main()
