"""Build fixed development and holdout sets from the CC0 Lichess puzzle CSV."""
import argparse
from collections import defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit


def stratum(row):
    themes = set(row['Themes'].split())
    if 'sacrifice' in themes and (themes & {'long', 'veryLong'}) and not any(
            theme.startswith('mateIn') or theme == 'mate' for theme in themes):
        return 'long_sacrifice'
    if 'defensiveMove' in themes and 'sacrifice' not in themes:
        return 'defense'
    if 'sacrifice' not in themes and themes & {'quietMove', 'mateIn3', 'promotion'}:
        return 'other_tactic'
    return None


def sample(rows, count, seed='tal087', excluded_games=()):
    # Split by source game before taking the lowest independent puzzle-ID hashes.
    # Keep at most one puzzle per game within a bucket and across the final sets.
    buckets = defaultdict(dict)
    for row in rows:
        if not (1500 <= int(row['Rating']) <= 2400 and int(row['Popularity']) >= 90
                and int(row['NbPlays']) >= 500):
            continue
        kind = stratum(row)
        if kind is None:
            continue
        game = urlsplit(row['GameUrl']).path.split('/')[1:]
        if not game:
            continue
        game = game[1] if game[0] == 'game' and len(game) > 1 else game[0]
        if game in excluded_games:
            continue
        split = 'development' if sha256(f'{seed}:game:{game}'.encode()).digest()[0] % 2 == 0 else 'holdout'
        key = sha256(f"{seed}:puzzle:{row['PuzzleId']}".encode()).hexdigest()
        by_game = buckets[split, kind]
        if game not in by_game or key < by_game[game][0]:
            by_game[game] = key, row

    import chess
    seen = set()
    sets = {'development': [], 'holdout': []}
    for split, kind in sorted(buckets):
        selected = 0
        for game, (_, row) in sorted(buckets[split, kind].items(), key=lambda item: item[1][0]):
            if game in seen:
                continue
            board = chess.Board(row['FEN'])
            source_board = board.copy()
            moves = row['Moves'].split()
            board.push_uci(moves[0])
            fen = board.fen(en_passant='fen')
            answer = board.san(chess.Move.from_uci(moves[1]))
            for move in moves[1:]:
                board.push_uci(move)
            sets[split].append(dict(id=f"lichess_{row['PuzzleId']}", fen=fen,
                                    puzzle_move=moves[1], answer_san=answer, category=kind,
                                    initial_fen=source_board.fen(en_passant='fen'), solution=moves,
                                    game=game, source=row['GameUrl'], rating=int(row['Rating']),
                                    themes=row['Themes'].split()))
            seen.add(game)
            selected += 1
            if selected == count:
                break
        if selected != count:
            raise ValueError(f'{split}/{kind} only has {selected} puzzles')
    if any(len(rows) != count * 3 for rows in sets.values()):
        raise ValueError('Input does not cover every split and category')
    return sets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-category', type=int, default=8)
    parser.add_argument('--seed', default='tal087')
    parser.add_argument('--exclude', type=Path, help='Earlier split JSON whose game IDs must be excluded.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.per_category < 1:
        parser.error('--per-category must be positive')
    import sys
    excluded = set()
    if args.exclude:
        excluded.update(row['game'] for split in json.loads(args.exclude.read_text()).values() for row in split)
    args.output.write_text(json.dumps(sample(csv.DictReader(sys.stdin), args.per_category, args.seed, excluded),
                                      indent=2) + '\n')


if __name__ == '__main__':
    main()
