"""Deterministic evaluation-only benchmark; not Elo or strength measurement."""
from pathlib import Path
from statistics import median
from time import perf_counter

import evaluate
from board import Board, START_FEN

FENS = [START_FEN] + [x for x in Path(__file__).with_name('v044_positions.txt').read_text().splitlines()
                      if x and not x.startswith('#')][::8]


def trial(initiative, activity, repeat=200):
    evaluate.INITIATIVE = initiative
    evaluate.ATTACK_ACTIVITY = activity
    boards = [Board(f) for f in FENS]
    for _ in range(5):
        for b in boards:
            evaluate.evaluate(b)
    samples = []
    checksum = 0
    for i in range(5):
        t0 = perf_counter()
        for _ in range(repeat):
            for b in boards:
                checksum += evaluate.evaluate(b)
        dt = perf_counter() - t0
        samples.append(dt / (repeat * len(boards)) * 1e6)
    return median(samples), checksum


def main():
    saved = (evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY)
    try:
        print('Median of five repeats, microseconds/evaluate(),',len(FENS),'positions')
        for ini, act in ((False, False), (True, False), (False, True), (True, True)):
            dt, val = trial(ini, act)
            print(f'Initiative={ini}, AttackActivity={act}: {dt:.2f} us/eval checksum={val}')
    finally:
        evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY = saved


if __name__ == '__main__':
    main()
