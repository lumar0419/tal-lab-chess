"""Run existing protocol assertions against the actual optional UCI process.

Unlike running test_uci through runpy alone, this overrides the child command.
Existing full test_uci.py still checks the portable engine and match tooling.
"""
import sys
import time
from pathlib import Path

import test_uci as suite


def main():
    root=Path(__file__).resolve().parents[1]
    suite.ENGINE_CMD=[sys.executable,str(root/'native_engine.py'),'uci']
    tests=(suite.test_handshake_and_basic,suite.test_time_controls,suite.test_stop_infinite,
        suite.test_terminal_and_history,suite.test_robustness,suite.test_v041_searchmoves_nodes,
        suite.test_v041_stop_races,suite.test_v041_ponder,suite.test_v041_hash,
        suite.test_v041_kingsafety_option,suite.test_v043_tactical_checks)
    start=time.monotonic()
    for test in tests:test()
    failed=[name for name,ok in suite.RESULTS if not ok]
    print(f'Actual Cython UCI process: {len(suite.RESULTS)-len(failed)}/{len(suite.RESULTS)} assertions, {time.monotonic()-start:.1f}s')
    if failed:raise SystemExit(', '.join(failed))


if __name__=='__main__':
    main()
