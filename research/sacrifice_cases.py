"""Legality-checked positions with historical labels, independent of discovery."""
import json
from pathlib import Path
from board import Board
from master_sacrifices import GAMES, build_cases, replay_san
from notation import san_for_move

ROOT = Path(__file__).resolve().parents[1]
ADDITIONAL = (
    {
        'id': 'morphy_opera_1858', 'master': 'Paul Morphy', 'year': 1858,
        'players': 'Paul Morphy – Duke of Brunswick and Count Isouard',
        'source': 'https://masterchess.live/famous-games/opera-game-morphy-1858',
        'san_moves': ('e4 e5 Nf3 d6 d4 Bg4 dxe5 Bxf3 Qxf3 dxe5 Bc4 Nf6 '
                      'Qb3 Qe7 Nc3 c6 Bg5 b5 Nxb5 cxb5 Bxb5+ Nbd7 O-O-O Rd8 '
                      'Rxd7 Rxd7 Rd1 Qe6 Bxd7+ Nxd7 Qb8+ Nxb8 Rd8#'),
        'cases': [(18, ['knight', 'line_opening', 'king_attack']),
                  (24, ['rook', 'defender_removal', 'line_opening']),
                  (28, ['bishop', 'defender_removal', 'serial']),
                  (30, ['queen', 'deflection', 'serial'])],
    },
    {
        'id': 'lasker_bauer_1889', 'master': 'Emanuel Lasker', 'year': 1889,
        'players': 'Emanuel Lasker – Johann Bauer',
        'source': 'https://chessmotion.com/explore/famous-chess-games/lasker-bauer-double-bishop-sacrifice',
        'san_moves': ('f4 d5 e3 Nf6 b3 e6 Bb2 Be7 Bd3 b6 Nf3 Bb7 Nc3 Nbd7 '
                      'O-O O-O Ne2 c5 Ng3 Qc7 Ne5 Nxe5 Bxe5 Qc6 Qe2 a6 Nh5 Nxh5 '
                      'Bxh7+ Kxh7 Qxh5+ Kg8 Bxg7 Kxg7 Qg4+ Kh7 Rf3 e5 Rh3+ Qh6 '
                      'Rxh6+ Kxh6 Qd7 Bf6'),
        'cases': [(28, ['bishop', 'king_attack', 'serial']),
                  (32, ['bishop', 'line_opening', 'serial', 'delayed_compensation'])],
    },
    {
        'id': 'levitsky_marshall_1912', 'master': 'Frank Marshall', 'year': 1912,
        'players': 'Stepan Levitsky – Frank Marshall',
        'source': 'https://www.chess.com/article/view/throwing-away-your-queen',
        'san_moves': ('d4 e6 e4 d5 Nc3 c5 Nf3 Nc6 exd5 exd5 Be2 Nf6 O-O Be7 '
                      'Bg5 O-O dxc5 Be6 Nd4 Bxc5 Nxe6 fxe6 Bg4 Qd6 Bh3 Rae8 Qd2 Bb4 '
                      'Bxf6 Rxf6 Rad1 Qc5 Qe2 Bxc3 bxc3 Qxc3 Rxd5 Nd4 Qh5 Ref8 '
                      'Re5 Rh6 Qg5 Rxh3 Rc5 Qg3'),
        'cases': [(45, ['queen', 'king_attack', 'deflection'])],
    },
    {
        'id': 'rotlewi_rubinstein_1907', 'master': 'Akiba Rubinstein', 'year': 1907,
        'players': 'Georg Rotlewi – Akiba Rubinstein',
        'source': 'https://chessmotion.com/explore/famous-chess-games/rotlewi-rubinstein-immortal',
        'san_moves': ('d4 d5 Nf3 e6 e3 c5 c4 Nc6 Nc3 Nf6 dxc5 Bxc5 a3 a6 b4 Bd6 '
                      'Bb2 O-O Qd2 Qe7 Bd3 dxc4 Bxc4 b5 Bd3 Rd8 Qe2 Bb7 O-O Ne5 '
                      'Nxe5 Bxe5 f4 Bc7 e4 Rac8 e5 Bb6+ Kh1 Ng4 Be4 Qh4 g3 Rxc3 '
                      'gxh4 Rd2 Qxd2 Bxe4+ Qg2 Rh3'),
        'cases': [(43, ['rook', 'queen', 'defender_removal', 'king_attack', 'serial']),
                  (45, ['rook', 'deflection', 'line_opening', 'serial'])],
    },
    {
        'id': 'karpov_kasparov_1985_g16', 'master': 'Garry Kasparov', 'year': 1985,
        'players': 'Anatoly Karpov – Garry Kasparov',
        'source': 'https://chessmotion.com/explore/famous-chess-games/karpov-kasparov-game-16',
        'san_moves': ('e4 c5 Nf3 e6 d4 cxd4 Nxd4 Nc6 Nb5 d6 c4 Nf6 N1c3 a6 '
                      'Na3 d5 cxd5 exd5 exd5 Nb4 Be2 Bc5 O-O O-O Bf3 Bf5 '
                      'Bg5 Re8 Qd2 b5 Rad1 Nd3'),
        'cases': [(15, ['pawn_offer', 'initiative', 'positional']),
                  (31, ['attack', 'outpost', 'positional'])],
    },
    {
        'id': 'reshevsky_petrosian_1953', 'master': 'Tigran Petrosian', 'year': 1953,
        'case_id': 'reshevsky_petrosian_1953_re6',
        'players': 'Samuel Reshevsky – Tigran Petrosian',
        'source': 'https://www.playstockfish.com/grandmastergames/game/reshevsky-vs-petrosian-1953-c9f5cb389800',
        'san_moves': ('d4 Nf6 c4 e6 Nc3 Bb4 e3 O-O Bd3 d5 Nf3 c5 O-O Nc6 a3 Bxc3 '
                      'bxc3 b6 cxd5 exd5 Bb2 c4 Bc2 Bg4 Qe1 Ne4 Nd2 Nxd2 Qxd2 Bh5 '
                      'f3 Bg6 e4 Qd7 Rae1 dxe4 fxe4 Rfe8 Qf4 b5 Bd1 Re7 Bg4 Qe8 '
                      'e5 a5 Re3 Rd8 Rfe1 Re6'),
        'cases': [(49, ['rook', 'positional', 'delayed_compensation', 'defensive'])],
    },
)
EXISTING_TAGS = [
    ['knight', 'king_attack'], ['queen', 'serial', 'delayed_compensation'],
    ['rook', 'line_opening', 'king_attack', 'serial'],
    ['rook', 'king_attack', 'serial'], ['rook', 'king_attack', 'delayed_compensation'],
    ['queen', 'deflection', 'serial'],
]


def positions():
    games = {g['id']: g for g in GAMES}
    result = []
    for case, tags in zip(build_cases(), EXISTING_TAGS, strict=True):
        history = [p['uci'] for p in replay_san(games[case['game_id']])]
        result.append({**case, 'themes': tags, 'history': history[:int(case['id'].split('_ply')[1])-1]})
    for game in ADDITIONAL:
        history = replay_san(game)
        for ply, tags in game['cases']:
            item = history[ply]
            result.append({k: game[k] for k in ('master', 'players', 'year', 'source')} | {
                'id': game.get('case_id', f"{game['id']}_ply{ply+1}"), 'fen': item['fen'],
                'historical_uci': item['uci'], 'historical_san': item['san'],
                'themes': tags, 'history': [p['uci'] for p in history[:ply]]})
    records = {g['id']: g for g in json.loads((ROOT/'tal_games.json').read_text())['games']}
    for case in json.loads((ROOT/'tal_positions.json').read_text())['positions']:
        if not case['featured'] and case['theme'] != 'bishop_sacrifice':
            continue
        game = records[case['game_id']]
        tags = ['knight' if 'knight' in case['theme'] else 'bishop', 'king_attack']
        if 'positional' in case['theme']:
            tags.extend(['positional', 'delayed_compensation'])
        result.append({'id': case['id'], 'master': 'Mikhail Tal', 'year': game['year'],
                       'players': game['players'], 'source': case['source'], 'fen': case['fen'],
                       'historical_uci': case['tal_move'], 'historical_san': case['san'],
                       'themes': tags, 'history': game['uci_moves'][:case['ply_before']]})
    return result


def replay_case(case):
    history = case.get('history')
    if history is None:
        board = Board(case['fen'])
    else:
        board = Board()
        for uci in history:
            board.push_uci(uci)
        if board.fen() != case['fen']:
            raise ValueError(f"FEN replay mismatch: {case['id']}")
    move = board.parse_uci(case['historical_uci'])
    if move is None or san_for_move(board, move) != case['historical_san']:
        raise ValueError(f"Historical move mismatch: {case['id']}")
    return board


if __name__ == '__main__':
    cases = positions()
    for case in cases:
        replay_case(case)
    print(json.dumps(cases, indent=2, ensure_ascii=False))
