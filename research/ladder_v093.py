"""한 국면을 정해진 시간 동안 반복 심화하고 완료한 깊이마다 기록한다 (v0.9.3 프로필 비교용).

    python -m research.ladder_v093 --case kasparov_topalov_1999_ply47 --profile tactical --seconds 300 --output out.json

--case는 evidence/v091/historical.json의 id, 또는 --fen으로 직접 국면을 준다. --source로 다른
버전의 폴더를 지정하면 그 엔진으로 같은 측정을 한다 ('tactical'은 v0.9.3부터).
"""
import argparse
import json
import platform
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--case')
    parser.add_argument('--fen')
    parser.add_argument('--source')
    parser.add_argument('--profile', choices=('tactical', 'conservative', 'full', 'selective'),
                        default='tactical')
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--tt', type=int, default=300_000, help='TT 항목 수')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.source).resolve() if args.source else Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from board import Board, WHITE
    from search import Searcher
    expected = None
    if args.case:
        cases = json.loads((Path(__file__).resolve().parents[1] / 'evidence' / 'v091' /
                            'historical.json').read_text('utf-8'))
        case = next(item for item in cases if item['id'] == args.case)
        fen, expected = case['fen'], case['historical_uci']
    elif args.fen:
        fen = args.fen
    else:
        parser.error('--case 또는 --fen이 필요합니다.')
    searcher = Searcher(tt_size=args.tt)
    searcher.lmr = args.profile == 'conservative'
    searcher.selective = args.profile == 'selective'
    if args.profile == 'tactical':
        searcher.set_tactical(True)
    rows = []
    board = Board(fen)
    white = board.side == WHITE
    report = dict(fen=fen, case=args.case, expected=expected, profile=args.profile, seconds=args.seconds,
                  tt_entries=args.tt, engine=str(root), python=sys.version.split()[0],
                  runtime=platform.python_implementation(), rows=rows)

    def collect(info):
        rows.append(dict(depth=info.depth, score_white=info.score if white else -info.score,
                         nodes=info.nodes, seconds=round(info.seconds, 2),
                         move=info.pv[0].uci() if info.pv else None,
                         pv=[move.uci() for move in info.pv]))
        Path(args.output).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
        print(args.case or 'fen', args.profile, rows[-1]['depth'], rows[-1]['score_white'],
              rows[-1]['seconds'], ' '.join(rows[-1]['pv'][:6]), flush=True)

    started = time.perf_counter()
    move, score = searcher.search(board, max_depth=64, time_limit=args.seconds, full_time=True,
                                  on_info=collect)
    report.update(final_move=move.uci() if move else None, elapsed=round(time.perf_counter() - started, 2),
                  matches_expected=(move.uci() == expected) if (move and expected) else None)
    Path(args.output).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
