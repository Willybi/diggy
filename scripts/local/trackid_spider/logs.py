"""Structured JSON logging (one JSON object per line) + a human console line.

Every event is emitted as a compact JSON line to an optional log file AND, in a
short human form, to stdout — so a run is both machine-parseable (progress /
throughput / ETA / per-window counters) and readable live.
"""

import functools
import json
import time

print = functools.partial(print, flush=True)  # noqa: A001 — keep piped output ordered


class JsonLogger:
    def __init__(self, log_path=None, clock=time.time):
        self._fh = open(log_path, "a", encoding="utf-8") if log_path else None
        self._clock = clock

    def close(self):
        if self._fh:
            self._fh.close()

    def event(self, kind, human=None, **fields):
        record = {"ts": round(self._clock(), 3), "event": kind, **fields}
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()
        if human is not None:
            print(human)
        return record


def format_eta(done, total, elapsed_s):
    """Rough ETA string from linear extrapolation (``?`` if not enough signal)."""
    if done <= 0 or total <= 0 or elapsed_s <= 0:
        return "?"
    rate = done / elapsed_s  # units/sec
    remaining = max(0, total - done)
    eta_s = remaining / rate if rate > 0 else 0
    mins, secs = divmod(int(eta_s), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:d}h{mins:02d}m{secs:02d}s"
