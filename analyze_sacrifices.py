"""Compare forcing or sacrificial candidate moves in the ONE existing engine.

This is a *diagnostic*, not a sacrifice reward, Tal-move classifier or a proof
that a speculative sacrifice is sound. Scores remain from the engine's search.

Examples:
  python analyze_sacrifices.py --fen "4k3/8/8/3q4/5N2/8/8/4K3 w - - 0 1" --depth 3 --moves f4d5
  python analyze_sacrifices.py --fen "6R1/5P1k/5KR1/8/8/8/8/8 w - - 0 1" --depth 3 --moves f7f8n f7f8q
"""
import argparse

import evaluate
from board import Board, WHITE, SQUARES
from search import Searcher, format_score, mate_plies

VALUES = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}


def material_for(board, side):
    total = 0
    for sq in SQUARES:
        piece = board.board[sq]
        if piece != '.':
            total += (1 if piece.isupper() == (side == WHITE) else -1) * VALUES[piece.upper()]
    return total


def inspect_line(board, pv):
    """Material after each PV ply. No claim of stable/adequate compensation."""
    initial = material_for(board, board.side)
    side = board.side
    copy = Board(board.fen())
    trail = []
    for move in pv:
        legal = copy.parse_uci(move.uci())
        if legal is None:
            break
        copy.make_move(legal)
        trail.append(material_for(copy, side) - initial)
    return trail


def compare_candidates(board, candidate_ucis, depth, initiative=False, activity=False,
                       checks=False):
    """Return rows for selected legal moves, with the engine's score and PV.

    Root-only filtering is supported by Searcher.search; do not alter the engine's
    actual move-selection rules, and reuse the same Searcher/TT among candidates.
    """
    original = (evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY)
    try:
        evaluate.INITIATIVE = bool(initiative)
        evaluate.ATTACK_ACTIVITY = bool(activity)
        searcher = Searcher(tt_size=30_000)
        searcher.qsearch_quiet_checks = bool(checks)
        allowed = {move.uci() for move in board.legal_moves()}
        candidates = list(dict.fromkeys(move.lower() for move in candidate_ucis))
        for move in candidates:
            if move not in allowed:
                raise ValueError(f'illegal candidate move: {move}')
        snap = board.snapshot()
        rows = []
        for move in candidates:
            info = []
            best, score = searcher.search(board, max_depth=depth, root_moves=[move],
                                          on_info=info.append)
            pv = info[-1].pv if info else ([best] if best is not None else [])
            rows.append({'move': move, 'score': score, 'pv': ' '.join(m.uci() for m in pv),
                         'material_delta_by_ply': inspect_line(board, pv),
                         'nodes': searcher.nodes})
            if board.snapshot() != snap:
                raise AssertionError('board changed during analysis')
        return rows
    finally:
        evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY = original



def score_gap_label(best, candidate):
    if mate_plies(best) is not None or mate_plies(candidate) is not None:
        return f'mate-sensitive ({format_score(best)} vs {format_score(candidate)})'
    return f'{best-candidate}cp'


def stockfish_review(board, candidate_ucis, stockfish_path, depth=16):
    """Optional independent UCI cross-check; requires python-chess + Stockfish.

    Scores are Stockfish's own root evaluations after forcing each candidate,
    not a declaration that a sacrifice is objectively sound or human-like.
    """
    try:
        import chess
        import chess.engine
    except ImportError as exc:
        raise RuntimeError("python-chess is needed only for Stockfish review: pip install chess") from exc
    import os
    import shutil
    binary = stockfish_path if os.path.isfile(stockfish_path) else shutil.which(stockfish_path)
    if binary is None:
        raise RuntimeError(f"Stockfish executable not found: {stockfish_path}")
    ref = chess.Board(board.fen())
    if ref.is_game_over(claim_draw=True):
        raise RuntimeError("Position is already finished; no candidate move to review")
    results = {}

    def summary(info):
        value = info['score'].pov(ref.turn)
        return {
            'score_cp_equivalent': value.score(mate_score=100_000),
            'mate_in_moves': value.mate(),
            'score': str(value),
            'depth': info.get('depth'),
            'pv': ' '.join(move.uci() for move in info.get('pv', [])),
        }

    # Uses the same strong external engine for every candidate. No limited-
    # strength option is used: a weak opponent is not a tactical correctness oracle.
    with chess.engine.SimpleEngine.popen_uci([binary]) as engine:
        best = summary(engine.analyse(ref, chess.engine.Limit(depth=depth)))
        for move_uci in candidate_ucis:
            move = chess.Move.from_uci(move_uci)
            if move not in ref.legal_moves:
                raise ValueError(f'Illegal Stockfish review candidate: {move_uci}')
            info = engine.analyse(ref, chess.engine.Limit(depth=depth), root_moves=[move])
            results[move_uci] = summary(info)
    return best, results


def main():
    parser = argparse.ArgumentParser(description='One-engine tactical sacrifice study')
    parser.add_argument('--fen', required=True)
    parser.add_argument('--depth', type=int, default=3)
    parser.add_argument('--moves', nargs='+', help='selected legal UCI moves (default: first 8)')
    parser.add_argument('--max-moves', type=int, default=8)
    parser.add_argument('--initiative', action='store_true')
    parser.add_argument('--activity', action='store_true')
    parser.add_argument('--tactical-checks', action='store_true')
    parser.add_argument('--stockfish', metavar='PATH', help='optional path to Stockfish executable for independent checking')
    parser.add_argument('--sf-depth', type=int, default=16, help='Stockfish analysis depth, not engine search depth')
    args = parser.parse_args()
    if not 1 <= args.depth <= 10:
        parser.error('depth must be 1..10 for diagnostic use')
    if not 1 <= args.sf_depth <= 100:
        parser.error('sf-depth must be 1..100')
    b = Board(args.fen)
    moves = args.moves or [m.uci() for m in b.legal_moves()[:args.max_moves]]
    rows = compare_candidates(b, moves, args.depth, args.initiative,
                              args.activity, args.tactical_checks)
    if not rows:
        print('No legal candidates')
        return
    best = max(row['score'] for row in rows)
    print('Moves are compared ONLY within the selected candidates.')
    print('Material deltas follow the truncated engine PV, not a verified forced line.')
    for row in sorted(rows, key=lambda r: r['score'], reverse=True):
        gap = score_gap_label(best, row['score'])
        print(f"{row['move']:6} score={format_score(row['score']):>7} gap={gap}"
              f" nodes={row['nodes']:,}  pv={row['pv']}"
              f"  material_delta={row['material_delta_by_ply']}")
    if args.stockfish:
        try:
            sf_best, sf_rows = stockfish_review(b, [row['move'] for row in rows],
                                               args.stockfish, args.sf_depth)
        except (RuntimeError, ValueError, OSError) as exc:
            parser.exit(2, f'Stockfish review unavailable: {exc}\n')
        print(f'Stockfish best (depth {args.sf_depth}): {sf_best["score"]} PV {sf_best["pv"]}')
        for row in sorted(rows, key=lambda r: r['score'], reverse=True):
            ext = sf_rows[row['move']]
            gap = sf_best['score_cp_equivalent'] - ext['score_cp_equivalent']
            # Mate scores are converted only for display; do not treat their
            # numeric gaps as ordinary centipawn errors.
            gap_label = f'{gap:+d} cp' if sf_best['mate_in_moves'] is None and ext['mate_in_moves'] is None else 'mate-sensitive'
            print(f'  {row["move"]}: Stockfish {ext["score"]}  '
                  f'gap_vs_SF_best={gap_label}  PV {ext["pv"]}')
        print('A single search depth does NOT prove that an attack or sacrifice is sound.')
    else:
        print('For independent tactical review, pass --stockfish PATH --sf-depth 16.')
    print('Do not classify a sacrifice as sound without deeper independent analysis.')


if __name__ == '__main__':
    main()
