"""Tests for the pure pairing logic of scripts/dedup_artists_deezer.

Only ``find_candidate_pairs`` is exercised — the pure, network-free heart of the
script (orphan↔holder pairing via the real accent fold). The Deezer confirmation
and the DB driver are network/DB I/O and are not unit-tested here.

Importing the script pulls ``workers.tasks.artists`` (for the real
``_norm_artist_name`` fold), which imports ``workers.celery_app`` at module load;
celery is not installed in the test env, so it is stubbed in ``sys.modules`` FIRST
— the same self-contained pattern as test_tasks_artist_backlog.py. The fold itself
(NFKD + ASCII) uses only ``unicodedata`` and runs for real.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
_API_PATH = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER_PATH, _API_PATH):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stub the infra modules the workers.tasks package imports at module load (celery
# machinery, redis, curl_cffi) — none are installed in the test env. Importing
# workers.tasks.artists runs workers/tasks/__init__.py, which pulls every task
# module, so the full set is stubbed (same list as test_tasks_artist_backlog.py).
for _mod in (
    "celery",
    "celery.schedules",
    "celery.signals",
    "celery._state",
    "redis",
    "redis.exceptions",
    "curl_cffi",
):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules.setdefault("workers.celery_app", MagicMock(celery_app=MagicMock()))

from scripts.dedup_artists_deezer import find_candidate_pairs  # noqa: E402


def _a(id, name, deezer_id=None):
    return SimpleNamespace(id=id, name=name, deezer_id=deezer_id)


class TestFindCandidatePairs:
    def test_accent_variant_pairs_with_single_holder(self):
        holder = _a(1, "Nick León", deezer_id="123")
        orphan = _a(2, "Nick Leon")  # ASCII-folds to the same key
        candidates, ambiguous = find_candidate_pairs([holder, orphan])

        assert ambiguous == []
        assert len(candidates) == 1
        c = candidates[0]
        assert c.orphan_id == 2
        assert c.holder_id == 1
        assert c.holder_deezer_id == "123"
        assert c.orphan_fold == "nick leon"

    def test_nfd_vs_nfc_form_pairs(self):
        # Same "Zoë" written decomposed (NFD) vs composed (NFC): NFKD+ASCII folds
        # both to "zoe", so the orphan pairs with the linked holder.
        import unicodedata

        holder = _a(1, unicodedata.normalize("NFC", "Zoë"), deezer_id="9")
        orphan = _a(2, unicodedata.normalize("NFD", "Zoë"))
        candidates, ambiguous = find_candidate_pairs([holder, orphan])

        assert len(candidates) == 1
        assert candidates[0].holder_id == 1

    def test_two_holders_same_fold_is_ambiguous(self):
        holder_a = _a(1, "Nick León", deezer_id="123")
        holder_b = _a(2, "Nick Leon", deezer_id="456")  # distinct artist, same fold
        orphan = _a(3, "níck leon")
        candidates, ambiguous = find_candidate_pairs([holder_a, holder_b, orphan])

        assert candidates == []
        assert len(ambiguous) == 1
        assert ambiguous[0].orphan_id == 3
        assert sorted(ambiguous[0].holder_ids) == [1, 2]

    def test_no_holder_is_skipped(self):
        orphan = _a(1, "Totally Unknown")
        candidates, ambiguous = find_candidate_pairs([orphan])

        assert candidates == []
        assert ambiguous == []

    def test_not_found_sentinel_is_not_a_holder(self):
        # A NOT_FOUND row is neither a holder nor an orphan → the orphan finds no
        # twin and is left alone (not merged into a confirmed-absent artist).
        sentinel = _a(1, "Nick Leon", deezer_id="NOT_FOUND")
        orphan = _a(2, "Nick León")
        candidates, ambiguous = find_candidate_pairs([sentinel, orphan])

        assert candidates == []
        assert ambiguous == []

    def test_exact_spelling_still_pairs(self):
        # Even without an accent difference, an unlinked twin of a linked artist
        # pairs (same fold, single holder) — the index blocked it from linking.
        holder = _a(1, "Boris Brejcha", deezer_id="10")
        orphan = _a(2, "Boris Brejcha")
        candidates, _ = find_candidate_pairs([holder, orphan])

        assert len(candidates) == 1
        assert candidates[0].holder_id == 1

    def test_two_orphans_share_one_holder(self):
        # Both accent variants fold into the same single linked twin.
        holder = _a(1, "Amélie Lens", deezer_id="77")
        orphan_a = _a(2, "Amelie Lens")
        orphan_b = _a(3, "AMÉLIE LENS")
        candidates, ambiguous = find_candidate_pairs([holder, orphan_a, orphan_b])

        assert ambiguous == []
        assert {c.orphan_id for c in candidates} == {2, 3}
        assert all(c.holder_id == 1 for c in candidates)

    def test_empty_name_never_pairs(self):
        holder = _a(1, "", deezer_id="1")  # empty fold → not indexed as a holder
        orphan = _a(2, "")  # empty fold → skipped
        candidates, ambiguous = find_candidate_pairs([holder, orphan])

        assert candidates == []
        assert ambiguous == []
