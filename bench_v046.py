"""Compare v0.4.5 vs v0.4.6 Initiative calculation within one engine.

Run: python bench_v046.py
Uses same static evaluation inputs and scoring, not an Elo/style measurement.
"""
from statistics import median
from time import perf_counter

import evaluate
from board import Board
from test_v046 import initiative_v045_adapter, sample_fens


def timed_evaluations(boards, part_function, batches=7, rounds=120):
    original = evaluate._initiative_parts
    evaluate._initiative_parts = part_function
    try:
        for _ in range(2):
            for b in boards:
                evaluate.evaluate(b)
        times, checksums = [], []
        for _ in range(batches):
            checksum = 0
            t0 = perf_counter()
            for _ in range(rounds):
                for b in boards:
                    checksum += evaluate.evaluate(b)
            times.append((perf_counter()-t0) * 1e6 / (rounds*len(boards)))
            checksums.append(checksum)
        assert len(set(checksums)) == 1
        return median(times), checksums[0]
    finally:
        evaluate._initiative_parts = original


def main():
    all_fens = sample_fens()
    # Fixed mix: some middlegames, random legal plays, promotions/endgames.
    fens = list(dict.fromkeys(all_fens[::max(1, len(all_fens)//28)]))[:32]
    boards = [Board(f) for f in fens]
    original_options = (evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY, evaluate.KING_SAFETY)
    new_impl = evaluate._initiative_parts
    try:
        evaluate.KING_SAFETY = False
        print(f'Initiative evaluation comparison ({len(boards)} FENs, 7 trials, median us/eval):')
        for activity in (False, True):
            evaluate.INITIATIVE = True
            evaluate.ATTACK_ACTIVITY = activity
            old_us, old_checksum = timed_evaluations(boards, initiative_v045_adapter)
            new_us, new_checksum = timed_evaluations(boards, new_impl)
            assert old_checksum == new_checksum, 'Evaluation values differ!'
            gain = (1-new_us/old_us)*100
            print(f'  AttackActivity={str(activity):5}: v0.4.5 {old_us:6.2f} us'
                  f'  v0.4.6 {new_us:6.2f} us  improvement={gain:+5.1f}%'
                  f'  checksum={new_checksum}')
    finally:
        evaluate.INITIATIVE, evaluate.ATTACK_ACTIVITY, evaluate.KING_SAFETY = original_options


if __name__ == '__main__':
    main()
