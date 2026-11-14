"""A single CPU slot for hosted searches, with bounded priority admission."""
from dataclasses import dataclass
import threading
import time

DEEP, AUTO, MANUAL, GAME = range(4)


@dataclass(eq=False)
class _Ticket:
    priority: int
    interrupted: threading.Event


class SearchGate:
    def __init__(self, max_waiters=32):
        self._condition = threading.Condition()
        self._owner = None
        self._waiters = []
        self._max_waiters = max_waiters

    def acquire_job(self, priority, interrupted, cancelled, timeout):
        """Fast jobs can interrupt deep jobs; manual and game jobs also preempt auto."""
        ticket = _Ticket(priority, interrupted)
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            if len(self._waiters) >= self._max_waiters or cancelled():
                return False
            self._waiters.append(ticket)
            try:
                if self._owner and self._owner.priority <= AUTO and priority > self._owner.priority:
                    self._owner.interrupted.set()
                while not cancelled():
                    if self._owner is None and ticket is max(self._waiters, key=lambda t: t.priority):
                        self._owner = ticket
                        return True
                    remaining = 0.05 if deadline is None else deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(min(0.05, remaining))
                return False
            finally:
                self._waiters.remove(ticket)
                self._condition.notify_all()

    def acquire(self, blocking=True):
        return self.acquire_job(MANUAL, threading.Event(), lambda: False, None if blocking else 0)

    def release(self):
        with self._condition:
            self._owner = None
            self._condition.notify_all()


def acquire_search(gate, priority, interrupted, cancelled, timeout):
    """Also accept a plain lock for local/worker compatibility."""
    if isinstance(gate, SearchGate):
        return gate.acquire_job(priority, interrupted, cancelled, timeout)
    deadline = None if timeout is None else time.monotonic() + timeout
    while not cancelled():
        if gate.acquire(blocking=False):
            return True
        remaining = 0.05 if deadline is None else deadline - time.monotonic()
        if remaining <= 0:
            break
        if gate.acquire(timeout=min(0.05, remaining)):
            return True
    return False
