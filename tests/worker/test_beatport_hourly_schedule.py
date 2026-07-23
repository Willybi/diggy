"""
Lot A — the Beatport enrichment moved from 2 long daily passes (06h + 15h,
~7h/8h limits) to ONE hourly bounded drain (6h-23h, batch_size=550/run, short
limits + hardened lock). A deploy kill now costs ≤1h instead of ~8h.

These are light source-level assertions (workers.celery_app pulls in celery,
which isn't installed outside Docker — same reason _read_visibility_timeout in
test_task_refactor.py reads the schedule from source rather than importing it).
"""
import os
import re

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")


def _celery_app_source():
    path = os.path.join(_SERVER_PATH, "workers", "celery_app.py")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _catalog_source():
    path = os.path.join(_SERVER_PATH, "workers", "tasks", "catalog.py")
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestBeatportHourlySchedule:
    def test_hourly_entry_present_with_expected_config(self):
        """The beat schedule carries the hourly Beatport drain: hour='6-23' and
        the batch_size=550 per-run cap."""
        source = _celery_app_source()
        assert "enrich-catalog-beatport-hourly" in source
        # crontab bounded to 6h-23h
        assert 'crontab(minute=0, hour="6-23")' in source
        # per-run cap passed as a beat kwarg
        assert '"batch_size": 550' in source
        # exactly one beat entry references the task now
        assert (
            source.count('"task": "workers.tasks.enrich_catalog_beatport"') == 1
        )

    def test_old_two_pass_entries_removed(self):
        """The former daily (06h) and afternoon (15h) passes are gone."""
        source = _celery_app_source()
        assert "enrich-catalog-beatport-daily" not in source
        assert "enrich-catalog-beatport-afternoon" not in source

    def test_lock_ttl_covers_beatport_time_limit(self):
        """Invariant: BEATPORT_LOCK_TTL ≥ the task's time_limit, so the lock
        cannot expire while a legitimate run is still in progress."""
        source = _catalog_source()

        ttl_match = re.search(r"BEATPORT_LOCK_TTL\s*=\s*(\d+)", source)
        assert ttl_match, "BEATPORT_LOCK_TTL constant not found"
        lock_ttl = int(ttl_match.group(1))

        # The enrich_catalog_beatport decorator's time_limit. The negative
        # lookbehind excludes the 'soft_time_limit=' substring match.
        tl_match = re.search(
            r'name="workers\.tasks\.enrich_catalog_beatport".*?'
            r"(?<![_a-z])time_limit=(\d+)",
            source,
            re.DOTALL,
        )
        assert tl_match, "enrich_catalog_beatport time_limit not found"
        time_limit = int(tl_match.group(1))

        assert lock_ttl >= time_limit, (
            f"BEATPORT_LOCK_TTL={lock_ttl} must be ≥ time_limit={time_limit}"
        )
