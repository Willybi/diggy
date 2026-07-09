"""Tests for server/workers/enrichment.py — async Deezer enrichment logic.

Focus: the private → shared promotion in _enrich_entry_async, which mirrors the
legacy synchronous path in deezer_enrich.enrich_entry (A3-01).
"""
import sys
from unittest.mock import MagicMock

# redis is not installed in the test env; enrichment.py imports it at module load.
# Save the original so we can restore after the import.
_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())

from workers.enrichment import _enrich_entry_async

# Restore sys.modules immediately — we already imported what we need.
# This prevents polluting other test files collected by pytest.
if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis


def _make_entry(**overrides):
    """Bare CatalogEntry-like mock; has_artwork=True skips the async cover upload."""
    entry = MagicMock()
    entry.id = 1
    entry.deezer_id = None
    entry.isrc = None
    entry.duration_ms = None
    entry.has_preview = False
    entry.has_artwork = True
    entry.scope = "private"
    entry.owner_id = 42
    for key, value in overrides.items():
        setattr(entry, key, value)
    return entry


class TestPromotePrivateToShared:
    async def test_promotes_private_on_deezer_match(self):
        entry = _make_entry(scope="private", owner_id=42)
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}

        changed = await _enrich_entry_async(entry, hit, pool, None, set())

        assert changed is True
        assert entry.deezer_id == "123"
        assert entry.scope == "shared"
        assert entry.owner_id is None

    async def test_keeps_shared_scope(self):
        entry = _make_entry(scope="shared", owner_id=7)
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": ""}

        changed = await _enrich_entry_async(entry, hit, pool, None, set())

        assert changed is True
        assert entry.scope == "shared"
        assert entry.owner_id == 7  # untouched: promotion only fires for 'private'

    async def test_no_change_keeps_private(self):
        # Entry already fully matches the hit → changed=False → no promotion.
        entry = _make_entry(
            scope="private",
            owner_id=42,
            deezer_id="123",
            isrc="US1234",
            duration_ms=180_000,
            has_preview=True,
            has_artwork=True,
        )
        pool = MagicMock()
        hit = {"id": 123, "isrc": "US1234", "duration": 180, "preview": "http://x"}

        changed = await _enrich_entry_async(entry, hit, pool, None, {"US1234"})

        assert changed is False
        assert entry.scope == "private"
        assert entry.owner_id == 42
