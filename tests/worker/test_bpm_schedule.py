"""E2.c — source-level assertions that the nightly BPM-analysis task is wired.

Light source reads (workers.celery_app pulls in celery, absent outside Docker —
same rationale as test_beatport_hourly_schedule.py): the beat entry (00h-03h,
batch_size 2000), the enrich-queue route, and the lock-TTL ≥ time_limit invariant.
"""
import os
import re

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")


def _read(*parts):
    with open(os.path.join(_SERVER_PATH, *parts), encoding="utf-8") as f:
        return f.read()


class TestBpmAnalysisWiring:
    def test_beat_entry_present_with_expected_config(self):
        source = _read("workers", "celery_app.py")
        assert "analyze-bpm-previews-hourly" in source
        # crontab bounded to 00h-03h
        assert 'crontab(minute=0, hour="0-3")' in source
        # per-run cap passed as a beat kwarg (2000 → 4 slots ≈ 8000/night)
        assert '"batch_size": 2000' in source
        # exactly one beat entry references the task
        assert source.count('"task": "workers.tasks.analyze_bpm_previews"') == 1

    def test_task_routed_to_enrich_queue(self):
        source = _read("workers", "celery_app.py")
        assert (
            '"workers.tasks.analyze_bpm_previews": {"queue": "enrich"}' in source
        )

    def test_task_reexported_for_autodiscover(self):
        source = _read("workers", "tasks", "__init__.py")
        assert "from workers.tasks.bpm import analyze_bpm_previews" in source
        assert '"analyze_bpm_previews"' in source

    def test_lock_ttl_covers_task_time_limit(self):
        """Invariant: ANALYSIS_BPM_LOCK_TTL ≥ the task's time_limit, so the lock
        cannot expire while a legitimate run is still in progress."""
        source = _read("workers", "tasks", "bpm.py")

        ttl_match = re.search(r'ANALYSIS_BPM_LOCK_TTL\s*=\s*int\(\s*os\.environ\.get\(\s*"[^"]+",\s*"(\d+)"', source)
        assert ttl_match, "ANALYSIS_BPM_LOCK_TTL default not found"
        lock_ttl = int(ttl_match.group(1))

        tl_match = re.search(
            r'name="workers\.tasks\.analyze_bpm_previews".*?'
            r"(?<![_a-z])time_limit=(\d+)",
            source,
            re.DOTALL,
        )
        assert tl_match, "analyze_bpm_previews time_limit not found"
        time_limit = int(tl_match.group(1))

        assert lock_ttl >= time_limit, (
            f"ANALYSIS_BPM_LOCK_TTL={lock_ttl} must be ≥ time_limit={time_limit}"
        )

    def test_no_autoretry_on_task(self):
        """The budget/lock is the loop guard — NO autoretry_for (a retry decorator
        turned a soft timeout into an infinite loop on the artist backlog)."""
        source = _read("workers", "tasks", "bpm.py")
        # the task decorator must not carry the autoretry_for kwarg (the docstring
        # documents its deliberate absence, so match the `=` assignment form).
        assert "autoretry_for=" not in source
