"""Tests for the C2c-3 UTF-8 stdout hardening of the set-artist backfill orchestrator
(worker/set_artist_backfill/backfill_set_artists.py).

The OPS import report echoes proposed links as "set title → artist" lines; on a
Windows cp1252 console the "→" raises UnicodeEncodeError mid-print and aborts the
run. We verify: `safe_print` never raises on a narrow console (and re-encodes
lossily), and `_configure_stdout` is a best-effort no-op on a non-reconfigurable
stream. The module imports only stdlib at load time (its server imports are none),
so it imports cleanly on the host — repo root on sys.path gives the `worker.*` path.
"""

import os
import sys

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../../")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from worker.set_artist_backfill import backfill_set_artists as bsa  # noqa: E402


class _NarrowStream:
    """A cp1252-like text stream: write() raises UnicodeEncodeError on non-cp1252
    content (exactly what a Windows console does on "→")."""

    encoding = "cp1252"

    def __init__(self):
        self.written = []

    def write(self, s):
        s.encode(self.encoding)  # raises UnicodeEncodeError on "→"
        self.written.append(s)
        return len(s)

    def flush(self):
        pass


class TestSafePrint:
    def test_survives_narrow_console_and_replaces_arrow(self, monkeypatch):
        stream = _NarrowStream()
        monkeypatch.setattr(sys, "stdout", stream)
        # Must NOT raise even though the raw "→" is uncodable in cp1252.
        bsa.safe_print("set title → Peggy Gou")
        joined = "".join(stream.written)
        assert "Peggy Gou" in joined
        assert "→" not in joined  # arrow was replaced lossily

    def test_plain_ascii_passes_through(self, monkeypatch):
        stream = _NarrowStream()
        monkeypatch.setattr(sys, "stdout", stream)
        bsa.safe_print("plain ascii report")
        assert "".join(stream.written).startswith("plain ascii report")

    def test_does_not_raise_on_utf8_stdout(self):
        # On a normal (test-captured) UTF-8 stdout the arrow just prints fine.
        bsa.safe_print("a → b")


class TestConfigureStdout:
    def test_reconfigures_when_supported(self, monkeypatch):
        calls = []

        class _S:
            def reconfigure(self, **kw):
                calls.append(kw)

        monkeypatch.setattr(sys, "stdout", _S())
        monkeypatch.setattr(sys, "stderr", _S())
        bsa._configure_stdout()
        assert {"encoding": "utf-8", "errors": "replace"} in calls

    def test_tolerates_non_reconfigurable_stream(self, monkeypatch):
        class _S:  # no reconfigure attribute
            pass

        monkeypatch.setattr(sys, "stdout", _S())
        monkeypatch.setattr(sys, "stderr", _S())
        bsa._configure_stdout()  # must not raise (AttributeError swallowed)
