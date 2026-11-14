"""
play.py — 터미널에서 내 엔진과 대국하기

  python play.py                # 내가 백, 엔진 생각 시간 3초
  python play.py --black        # 내가 흑
  python play.py --time 10      # 엔진 생각 시간 10초
  python play.py --fen "<FEN>"  # 특정 국면에서 시작

입력
  e2e4        수 두기 (UCI 표기: 출발 칸 + 도착 칸, 승격은 e7e8q)
  moves       지금 둘 수 있는 수 보기
  draw        무승부 청구: 지금 국면이 50수 규칙 / 3회 동형반복일 때 (FIDE 9.2.1.2, 9.3.2)
  draw e1d1   무승부 청구: '이 수를 두면' 50수 / 3회 반복이 될 때 (FIDE 9.2.1.1, 9.3.1)
  undo        한 수 무르기 (내 수 + 엔진 수)
  quit        끝내기

무승부 규칙
  자동 종료     스테일메이트, 기물 부족, 75수 규칙, 5회 동형반복 → 바로 끝남
  청구해야 끝남 50수 규칙, 3회 동형반복 → 사람은 'draw', 엔진은 이길 수 없다고 볼 때 청구
                · 지금 국면이 청구 가능하고 엔진 점수 ≤ 0 → 청구
                · 엔진이 고른 수가 청구 가능한 국면을 만들고 엔진 점수 ≤ 0 → 그 수를 두며 청구
                (청구 가능한 국면에서는 상대도 곧 청구할 수 있어서 지는 쪽의 점수가 0으로 나옴)
"""

import sys

from board import Board, WHITE, BLACK, START_FEN, sq
from search import Searcher, format_score


def show(b, flip):
    ranks = range(8) if flip else range(7, -1, -1)
    files = range(7, -1, -1) if flip else range(8)
    for r in ranks:
        print(f"{r + 1}  " + ' '.join(b.board[sq(f, r)] for f in files))
    print("   " + ' '.join('abcdefgh'[f] for f in files))


def arg_value(args, name, default):
    return args[args.index(name) + 1] if name in args else default


def claim_after(b, m):
    """수 m을 두면 청구 가능한 무승부가 되는지 (사유 또는 None). 보드는 그대로 둠."""
    b.make_move(m)
    try:
        return b.claimable_draw()
    finally:
        b.unmake_move()


def main():
    args = sys.argv[1:]
    human = BLACK if '--black' in args else WHITE
    try:
        think = float(arg_value(args, '--time', 3))
        b = Board(arg_value(args, '--fen', START_FEN))
    except (ValueError, IndexError) as e:      # 잘못된 FEN·시간 값: 오류 메시지만 보여 주고 종료
        print(f"시작할 수 없어요: {e}")
        sys.exit(2)
    engine = Searcher()
    print("대문자 = 백, 소문자 = 흑.  'moves' 합법수 / 'draw' 무승부 청구 / 'undo' 무르기 / 'quit' 종료")

    while True:
        print()
        show(b, flip=(human == BLACK))
        result = b.outcome()                     # 자동 종료 (청구 없이 끝나는 경우)
        if result:
            print(f"\n대국 종료 (자동): {result[0]}  — {result[1]}")
            break
        if b.in_check():
            print("체크!")
        claim = b.claimable_draw()               # 청구해야 끝나는 경우

        if b.side == human:
            if claim:
                print(f"무승부 청구 가능: {claim}  ('draw' 입력)")
            try:
                text = input("\n당신의 수> ").strip().lower()
            except EOFError:
                break
            if text in ('quit', 'exit', 'q'):
                break
            if text == 'moves':
                print(' '.join(sorted(m.uci() for m in b.legal_moves())))
                continue
            if text == 'draw':
                if claim:
                    print(f"\n대국 종료 (청구): 1/2-1/2  — 당신의 청구: {claim}")
                    break
                print("지금은 무승부를 청구할 수 없어요.")
                continue
            if text.startswith('draw '):
                m = b.parse_uci(text[5:])
                reason = claim_after(b, m) if m else None
                if reason:
                    print(f"\n대국 종료 (청구): 1/2-1/2  — 당신이 {m.uci()}를 두며 청구: {reason}")
                    break
                print("그 수로는 무승부를 청구할 수 없어요.")
                continue
            if text == 'undo':
                if len(b.history) >= 2:
                    b.unmake_move()
                    b.unmake_move()
                else:
                    print("무를 수가 없어요.")
                continue
            m = b.parse_uci(text)
            if m is None:
                print("둘 수 없는 수예요. 'moves'를 입력하면 둘 수 있는 수가 나와요.")
                continue
            b.make_move(m)
        else:
            print(f"\n엔진 생각 중… (최대 {think:g}초)")
            m, score = engine.search(b, time_limit=think)
            if m is None:                        # 이미 끝난 국면 (위에서 걸러지지만 안전장치)
                ended = b.outcome()
                print(f"\n대국 종료 (자동): {ended[0] if ended else '?'}  — {ended[1] if ended else ''}")
                break
            if claim and score <= 0:
                print(f"\n대국 종료 (청구): 1/2-1/2  — 엔진의 청구: {claim}")
                break
            reason = claim_after(b, m)
            if reason and score <= 0:
                print(f"\n대국 종료 (청구): 1/2-1/2  — 엔진이 {m.uci()}를 두며 청구: {reason}")
                break
            b.make_move(m)
            print(f"엔진의 수: {m.uci()}   엔진이 본 형세(엔진 기준): {format_score(score)}")


if __name__ == '__main__':
    main()
