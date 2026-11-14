"""Strict bounded single-game PGN mainline import using Tal's own legal moves.
Comments/NAGs/RAVs are ignored, never mistaken for mainline moves.
"""
import re
from board import Board, START_FEN
from notation import san_for_move

MAX_PGN_BYTES = 131072
MAX_PLIES = 600

def normalize(token):
    return re.sub(r'[+#?!]+$', '', token.replace('0-0', 'O-O'))

def parse_pgn(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_PGN_BYTES:
        raise ValueError('PGN은 UTF-8 기준 128 KiB 이하로 입력하세요.')
    # Tokenize tags, comments and recursive variations without greedy stripping.
    tags, tokens, depth, i = {}, [], 0, 0
    while i < len(text):
        c = text[i]
        if c.isspace(): i += 1; continue
        if c == ';':
            end = text.find('\n', i); i = len(text) if end < 0 else end + 1; continue
        if c == '{':
            end = text.find('}', i)
            if end < 0: raise ValueError('닫히지 않은 PGN 주석입니다.')
            i = end + 1; continue
        if c == '(':
            depth += 1
            if depth > 32: raise ValueError('PGN 변형 수순이 너무 깊습니다.')
            i += 1; continue
        if c == ')':
            if depth == 0: raise ValueError('PGN 괄호가 맞지 않습니다.')
            depth -= 1; i += 1; continue
        if c == '[':
            m = re.match(r'\[([A-Za-z0-9_]+)\s+"((?:[^"\\]|\\.)*)"\s*\]', text[i:])
            if not m or tokens or depth: raise ValueError('PGN 헤더 또는 여러 대국 입력을 확인하세요.')
            tags[m[1]] = re.sub(r'\\(["\\])', r'\1', m[2]); i += len(m[0]); continue
        m = re.match(r'[^\s{}();\[\]]+', text[i:])
        if not m: raise ValueError('지원하지 않는 PGN 구문입니다.')
        if not depth: tokens.append(m[0])
        i += len(m[0])
    if depth: raise ValueError('닫히지 않은 PGN 변형 수순입니다.')
    if tags.get('Variant', 'Standard').lower() not in ('standard', 'chess'):
        raise ValueError('표준 체스 PGN만 지원합니다.')
    if tags.get('SetUp') == '1' and 'FEN' not in tags:
        raise ValueError('SetUp=1에는 FEN 헤더가 필요합니다.')
    board = Board(tags.get('FEN', START_FEN)); base = board.fen(); moves = []; ended = False
    for token in tokens:
        token = re.sub(r'^\d+\.(?:\.\.)?', '', token)
        token = re.sub(r'\$\d+', '', token)
        if not token or token == '...' or re.fullmatch(r'[!?]+', token): continue
        if token in ('1-0', '0-1', '1/2-1/2', '*'):
            if ended: raise ValueError('한 번에 한 대국만 불러올 수 있습니다.')
            ended = True; continue
        if ended: raise ValueError('결과 이후에 수가 있습니다. 한 대국만 입력하세요.')
        if len(moves) >= MAX_PLIES: raise ValueError('최대 600 반수까지 지원합니다.')
        if board.outcome() is not None: raise ValueError('종료된 국면 뒤에 수가 있습니다.')
        target = normalize(token)
        candidates = [(m, san_for_move(board, m)) for m in board.legal_moves()]
        found = [(m, san) for m, san in candidates if normalize(san) == target]
        if len(found) != 1: raise ValueError(f'{len(moves)+1}번째 반수 {token!r}: SAN이 모호하거나 불법입니다.')
        move, san = found[0]; moves.append({'uci': move.uci(), 'san': san}); board.make_move(move)
    return {'base_fen': base, 'moves': moves, 'tags': tags}
