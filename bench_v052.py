"""Evaluate v0.5.2 Tal-style speed with reproducible historic positions.

Run: python bench_v052.py
For a v0.5.1 vs v0.5.2 comparison, provide --reference PATH_TO_v051_evaluate.py.
No package dependencies.
"""
import argparse
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from board import Board
import evaluate


def load(path):
    spec = importlib.util.spec_from_file_location('reference_evaluate_v051', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def trial(mod, boards, loops):
    mod.ATTACK_ACTIVITY = True
    mod.INITIATIVE = True
    mod.KING_SAFETY = False
    mod.clear_pawn_cache()
    for b in boards:
        mod.evaluate_white(b)
    starts = perf_counter()
    checks = 0
    for _ in range(loops):
        for board in boards:
            checks += mod.evaluate_white(board)
    return (perf_counter() - starts) * 1e6 / (loops * len(boards)), checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, default=None)
    parser.add_argument('--loops', type=int, default=200)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    data = json.loads((Path(__file__).parent / 'tal_positions.json').read_text())
    boards = [Board(p['fen']) for p in data['positions']]
    baseline = load(args.reference) if args.reference else None
    samples = {'v0.5.2': []}
    if baseline: samples['reference'] = []
    for _ in range(args.repeats):
        for name, mod in (('reference', baseline), ('v0.5.2', evaluate)):
            if mod is None: continue
            runtime, checksum = trial(mod, boards, args.loops)
            samples[name].append(runtime)
            print(f'{name}: {runtime:.2f} us/eval, checksum {checksum}')
    if baseline:
        print('v0.5.1 / v0.5.2 median:',
              round(median(samples['reference']) / median(samples['v0.5.2']), 3), 'x')


if __name__ == '__main__':
    main()
