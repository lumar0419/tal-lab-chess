"""전술 모음(JSON)을 한 설정으로 풀거나, 두 결과를 비교한다.

    python -m research.suite_runner run --suite suite.json --output new.json --seconds 1 --profile selective --only wac
    python -m research.suite_runner run --engine /path/to/v087 --suite suite.json --output base.json --seconds 1
    python -m research.suite_runner compare --suite suite.json base.json new.json

--engine을 주면 그 폴더의 board.py·search.py를 쓴다 (다른 버전과 같은 조건으로 비교). 국면마다
새 Searcher, MultiPV 1, 시간 제한은 search(time_limit=초). 정답 = 최종 수가 bm에 포함.
"""
import argparse
import json
import sys
import time
from pathlib import Path


def run(args):
    root = Path(args.engine).resolve() if args.engine else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from board import Board
    from search import Searcher
    options = json.loads(args.options) if args.options else {}
    if args.profile:
        from research.tactical_profiles import PROFILES
        options = {**PROFILES[args.profile], **options}
    cases = json.load(open(args.suite, encoding='utf-8'))
    if args.only:
        wanted = set(args.only)
        cases = [case for case in cases if case['suite'] in wanted]
    cases = cases[args.shard::args.shards]
    rows = []
    for case in cases:
        searcher = Searcher()
        for key, value in options.items():
            if not hasattr(searcher, key):
                raise SystemExit(f'unknown search option: {key}')
            setattr(searcher, key, value)
        samples = []
        events = []
        if args.trace and hasattr(searcher, 'selective_trace'):
            wanted = set(case['bm']) | set(case.get('diagnose_moves', ()))

            def trace(event, board, ply, depth, move):
                if searcher._after_null or ply > 4 or len(events) >= 160:
                    return
                path = [entry[0].uci() for entry in board.history]
                if path and path[0] in wanted:
                    events.append(dict(event=event, path=path, remaining=depth,
                                       fen=board.fen(), ply=ply,
                                       move=move.uci() if move else None))

            searcher.selective_trace = trace

        def collect(group):
            samples.append({'depth': group[0].depth, 'nodes': searcher.nodes,
                            'seconds': group[-1].seconds, 'lines': [
                {'score': line.score, 'pv': [move.uci() for move in line.pv]} for line in group]})
        started = time.perf_counter()
        limits = ({'max_depth': args.depth} if args.depth else {'node_limit': args.nodes}
                  if args.nodes else {'time_limit': args.seconds})
        board = Board(case['fen'])
        before = board.snapshot()
        move, score = searcher.search(board, on_info=(lambda line: collect([line])) if args.multipv == 1 else None,
                                      multipv=args.multipv, on_multipv=collect if args.multipv > 1 else None,
                                      **limits)
        if before != board.snapshot():
            raise RuntimeError(f"Search changed the position of {case['id']}")
        answer = move.uci() if move else None
        final = samples[-1] if samples else {'depth': 0, 'lines': []}
        moves = [line['pv'][0] for line in final['lines'] if line['pv']]
        elapsed = time.perf_counter() - started
        rows.append({'id': case['id'], 'expected': case['bm'], 'move': answer,
                     'ok': answer in case['bm'], 'rank': next((i for i, move in enumerate(moves, 1)
                                                                if move in case['bm']), None),
                     'score': score, 'depth': final['depth'], 'nodes': searcher.nodes,
                     'time': round(elapsed, 3), 'nps': round(searcher.nodes / elapsed),
                     'iterations': samples, 'pruning': getattr(searcher, 'sel_stats', {}),
                     'trace': events})
    with open(args.output, 'w', encoding='utf-8') as handle:
        json.dump({'engine': str(root), 'seconds': args.seconds, 'depth': args.depth, 'node_limit': args.nodes,
                   'options': options, 'multipv': args.multipv, 'rows': rows}, handle)
    solved = sum(row['ok'] for row in rows)
    print(f'{solved}/{len(rows)} solved, mean completed depth '
          f'{sum(row["depth"] for row in rows) / max(len(rows), 1):.2f}')


def compare(args):
    suite = {case['id']: case for case in json.load(open(args.suite, encoding='utf-8'))}
    first = {row['id']: row for row in json.load(open(args.first, encoding='utf-8'))['rows']}
    second = {row['id']: row for row in json.load(open(args.second, encoding='utf-8'))['rows']}
    ids = [key for key in first if key in second]
    for label, chosen in (('all', ids),
                          ('sacrifice (SEE <= -100)', [k for k in ids if suite[k].get('sacrifice')]),
                          ('piece sacrifice (SEE <= -300)', [k for k in ids if suite[k].get('see', 0) <= -300])):
        gained = sum(second[k]['ok'] and not first[k]['ok'] for k in chosen)
        lost = sum(first[k]['ok'] and not second[k]['ok'] for k in chosen)
        print(f'{label}: {sum(first[k]["ok"] for k in chosen)} -> {sum(second[k]["ok"] for k in chosen)} '
              f'of {len(chosen)} (gained {gained}, lost {lost})')
    print(f'mean completed depth: {sum(first[k]["depth"] for k in ids) / len(ids):.2f} -> '
          f'{sum(second[k]["depth"] for k in ids) / len(ids):.2f}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    runner = commands.add_parser('run')
    runner.add_argument('--engine')
    runner.add_argument('--suite', required=True)
    runner.add_argument('--output', required=True)
    runner.add_argument('--seconds', type=float, default=1.0)
    runner.add_argument('--depth', type=int)
    runner.add_argument('--nodes', type=int, help='고정 노드 수 (시간 잡음 없이 재현 가능한 비교)')
    runner.add_argument('--multipv', type=int, choices=(1, 3), default=1)
    runner.add_argument('--trace', action='store_true', help='Record selected pruning events in root candidate lines.')
    runner.add_argument('--shard', type=int, default=0)
    runner.add_argument('--shards', type=int, default=1)
    runner.add_argument('--profile')
    runner.add_argument('--options', help='JSON object of Searcher attributes')
    runner.add_argument('--only', nargs='+', help='suite names to keep')
    runner.set_defaults(action=run)
    comparer = commands.add_parser('compare')
    comparer.add_argument('--suite', required=True)
    comparer.add_argument('first')
    comparer.add_argument('second')
    comparer.set_defaults(action=compare)
    args = parser.parse_args()
    if args.command == 'run' and not 0 <= args.shard < args.shards:
        parser.error('--shard must be within --shards')
    args.action(args)


if __name__ == '__main__':
    main()
