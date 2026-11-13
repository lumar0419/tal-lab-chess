"""Verified historical sacrifice position extraction and fixed-depth benchmarking.

Historical notation is a label, not a claim that the move is the computer's best move.
The dataset contains the MOVES UP TO the tested positions; it is not training data.
No external chess package is required: SAN is validated against our legal-move
engine, and the archived FEN positions are checked by replaying their score.
"""
import argparse
import json
import re
import time
from pathlib import Path

import evaluate
from board import Board
from search import Searcher, format_score
from web_server import san_for_move

HERE = Path(__file__).resolve().parent

# These are historical move scores through (or past) the featured positions.
# Sources are linked for provenance, and the SAN is independently replayed.
GAMES = [
    {
        'id': 'fischer_byrne_1956', 'master': 'Bobby Fischer',
        'players': 'Donald Byrne – Bobby Fischer', 'year': 1956,
        'source': 'https://www.chessworld.net/chessclubs/openingguide/game-of-the-century.asp',
        'san_moves': '''Nf3 Nf6 c4 g6 Nc3 Bg7 d4 O-O Bf4 d5 Qb3 dxc4 Qxc4 c6
                       e4 Nbd7 Rd1 Nb6 Qc5 Bg4 Bg5 Na4 Qa3 Nxc3 bxc3 Nxe4
                       Bxe7 Qb6 Bc4 Nxc3 Bc5 Rfe8+ Kf1 Be6 Bxb6 Bxc4+''',
        'cases': [
            {'ply': 21, 'label': '11...Na4', 'theme': '나이트를 공격받는 칸에 두는 전술', 'tag': 'knight_offer'},
            {'ply': 33, 'label': '17...Be6', 'theme': '퀸을 피하지 않고 전술적 보상을 택함', 'tag': 'queen_offer'},
        ],
    },
    {
        'id': 'kasparov_topalov_1999', 'master': 'Garry Kasparov',
        'players': 'Garry Kasparov – Veselin Topalov', 'year': 1999,
        'source': 'https://github.com/kerry-huang-nyu/chessRobot/blob/main/kasparov_topalov_1999.pgn',
        'san_moves': '''e4 d6 d4 Nf6 Nc3 g6 Be3 Bg7 Qd2 c6 f3 b5 Nge2 Nbd7
                       Bh6 Bxh6 Qxh6 Bb7 a3 e5 O-O-O Qe7 Kb1 a6 Nc1 O-O-O
                       Nb3 exd4 Rxd4 c5 Rd1 Nb6 g3 Kb8 Na5 Ba8 Bh3 d5
                       Qf4+ Ka7 Rhe1 d4 Nd5 Nbxd5 exd5 Qd6 Rxd4 cxd4 Re7+ Kb6
                       Qxd4+ Kxa5 b4+ Ka4''',
        'cases': [
            {'ply': 46, 'label': '24.Rxd4', 'theme': '공격선을 여는 룩 희생', 'tag': 'rook_sacrifice'},
            {'ply': 48, 'label': '25.Re7+', 'theme': '첫 희생 후 강제 체크 수순', 'tag': 'rook_offer'},
        ],
    },
    {
        'id': 'anderssen_kieseritzky_1851', 'master': 'Adolf Anderssen',
        'players': 'Adolf Anderssen – Lionel Kieseritzky', 'year': 1851,
        # Traditional continuation may differ from early historical recordings.
        'source': 'https://huggingface.co/datasets/tms-gvd/chess-game1-white/blob/main/anderssen_kieseritzky_1851.pgn',
        'san_moves': '''e4 e5 f4 exf4 Bc4 Qh4+ Kf1 b5 Bxb5 Nf6 Nf3 Qh6
                       d3 Nh5 Nh4 Qg5 Nf5 c6 g4 Nf6 Rg1 cxb5 h4 Qg6
                       h5 Qg5 Qf3 Ng8 Bxf4 Qf6 Nc3 Bc5 Nd5 Qxb2 Bd6 Bxg1
                       e5 Qxa1+ Ke2 Na6 Nxg7+ Kd8 Qf6+ Nxf6 Be7#''',
        'cases': [
            {'ply': 34, 'label': '18.Bd6', 'theme': '전술적 주도권을 위한 비숍 전개', 'tag': 'attack_initiative'},
            {'ply': 42, 'label': '22.Qf6+', 'theme': '강제 메이트를 위한 퀸 희생', 'tag': 'queen_sacrifice'},
        ],
    },
]


def _normalized(s):
    return re.sub(r'[+#!?]', '', s.replace('0', 'O')).strip()


def replay_san(game):
    board = Board()
    positions = []
    for ply, san in enumerate(game['san_moves'].split()):
        choice = []
        for m in board.legal_moves():
            if _normalized(san_for_move(board, m)) == _normalized(san):
                choice.append(m)
        if len(choice) != 1:
            raise ValueError(f'{game["id"]} ply={ply} SAN={san!r}, matches={len(choice)}')
        m = choice[0]
        positions.append({'ply': ply, 'fen': board.fen(), 'san': san,
                          'uci': m.uci()})
        board.make_move(m)
    return positions


def build_cases():
    cases = []
    for game in GAMES:
        positions = replay_san(game)
        for desired in game['cases']:
            p = positions[desired['ply']]
            cases.append({
                'id': f'{game["id"]}_ply{p["ply"] + 1}',
                'game_id': game['id'], 'master': game['master'],
                'players': game['players'], 'year': game['year'],
                'source': game['source'], 'fen': p['fen'],
                'historical_san': p['san'], 'historical_uci': p['uci'],
                'label': desired['label'], 'theme': desired['theme'],
                'tag': desired['tag'],
                'status': 'historical move; not independently verified as objectively best',
            })
    return cases


def verify_dataset():
    cases = build_cases()
    saved = json.loads((HERE / 'master_sacrifice_cases.json').read_text(encoding='utf-8'))['positions']
    if cases != saved:
        raise AssertionError('Historical dataset differs from independently replayed legal moves')
    for case in cases:
        b = Board(case['fen'])
        if b.parse_uci(case['historical_uci']) is None:
            raise AssertionError('Illegal historical move: ' + case['id'])
    return cases


def benchmark(depth=3, seconds=None, lmr=False, include_tal=True, stockfish=None, sf_depth=16, case_ids=None):
    if not 1 <= depth <= 8:
        raise ValueError('depth must be 1..8')
    cases = verify_dataset()
    if include_tal:
        tal = json.loads((HERE / 'tal_positions.json').read_text(encoding='utf-8'))['positions']
        for c in tal:
            if not c.get('featured'):
                continue
            cases.append({'id': c['id'], 'master': 'Mikhail Tal',
                          'fen': c['fen'], 'historical_uci': c['tal_move'],
                          'historical_san': c['san'], 'label': c['san'],
                          'theme': c['theme'], 'source': c['source']})
    if case_ids is not None:
        cases = [c for c in cases if c['id'] in case_ids]
        if len(cases) != len(case_ids):
            raise ValueError('Unknown case id(s): ' + ', '.join(set(case_ids) - {c['id'] for c in cases}))
    rows = []
    original = (evaluate.KING_SAFETY, evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE)
    evaluate.KING_SAFETY = False
    evaluate.ATTACK_ACTIVITY = False
    evaluate.INITIATIVE = False
    try:
        for case in cases:
            board = Board(case['fen'])
            initial = board.snapshot()
            engine = Searcher(tt_size=50_000)
            engine.lmr = lmr
            start = time.perf_counter()
            chosen, score = engine.search(board, max_depth=depth, time_limit=seconds, on_info=lambda info: None)
            if board.snapshot() != initial:
                raise AssertionError('Search damaged the board')
            # Do NOT call every differing choice a blunder; historical moves can
            # be speculative/suboptimal, and fixed-depth eval is not ground truth.
            row = {
                'id': case['id'], 'master': case['master'], 'label': case['label'],
                'historical': case['historical_uci'],
                'engine_choice': chosen.uci() if chosen else None,
                'matched': chosen is not None and chosen.uci() == case['historical_uci'],
                'score': format_score(score), 'nodes': engine.nodes,
                'seconds': round(time.perf_counter() - start, 3),
                'lmr_probes': engine.lmr_probes, 'source': case['source'],
            }
            if stockfish:
                # Real external tactical review; no heuristic 'brilliant' label.
                from analyze_sacrifices import stockfish_review
                choices = list(dict.fromkeys((case['historical_uci'], row['engine_choice'])))
                sf_best, sf_candidates = stockfish_review(board, choices, stockfish, sf_depth)
                row['stockfish'] = {'best': sf_best, 'candidates': sf_candidates,
                                    'depth_requested': sf_depth}
            rows.append(row)
    finally:
        evaluate.KING_SAFETY, evaluate.ATTACK_ACTIVITY, evaluate.INITIATIVE = original
    return rows


def main():
    parser = argparse.ArgumentParser(description='Multi-master historical choice benchmark (not an Elo rating)')
    parser.add_argument('--depth', type=int, default=3)
    parser.add_argument('--seconds', type=float, default=None)
    parser.add_argument('--lmr', action='store_true')
    parser.add_argument('--output', default=None)
    parser.add_argument('--only-new', action='store_true', help='exclude existing Mikhail Tal dataset')
    parser.add_argument('--case', action='append', help='test exact case ID, repeatable')
    parser.add_argument('--stockfish', help='optional Stockfish executable to independently review sacrifices')
    parser.add_argument('--sf-depth', type=int, default=16)
    args = parser.parse_args()
    rows = benchmark(args.depth, args.seconds, args.lmr, include_tal=not args.only_new,
                     stockfish=args.stockfish, sf_depth=args.sf_depth,
                     case_ids=set(args.case) if args.case else None)
    for r in rows:
        print(f"{r['master']:<17} {r['label']:<12} "
              f"historical={r['historical']:<6} engine={str(r['engine_choice']):<6} "
              f"{'MATCH' if r['matched'] else 'different':<9} "
              f"score={r['score']:>7} nodes={r['nodes']:,} time={r['seconds']}s", flush=True)
    print(f"Historical match: {sum(r['matched'] for r in rows)}/{len(rows)} "
          '(not Elo or objective correctness)')
    if args.output:
        out = {'depth': args.depth, 'lmr': args.lmr, 'seconds': args.seconds,
               'stockfish_path': args.stockfish, 'sf_depth': args.sf_depth,
               'disclaimer': 'Historical match does not imply optimality or soundness. Validate with Stockfish.',
               'results': rows}
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
