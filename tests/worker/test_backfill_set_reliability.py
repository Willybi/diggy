"""Tests for the C8 L3 OPS backfill script (scripts/backfill_set_reliability).

Exercises the testable cores ``backfill_reliability`` and ``backfill_source_url``
(extracted from ``main`` so they run without the CLI) against a real sync SQLite
session (``sync_session`` fixture). The reliability decision reuses L1's
``compute_set_unreliable`` — these tests assert the SELECTION + wiring (counts,
effective source_url, placeholder probe, idempotence), NOT the threshold itself
(that is L1's own test's job).

The MinIO placeholder read is INJECTED (``placeholder_probe``) so the decision
logic is covered without standing up MinIO/boto — the only part left uncovered is
``_placeholder_from_minio`` (a thin boto get_object + md5 that needs a live bucket;
its failure path is a plain try/except returning False). Same import/path pattern
as test_reverify_platform_ids.py.
"""
import itertools
import os
import sys

# Make server/api importable (same pattern as test_reverify_platform_ids.py).
_SERVER_API = os.path.join(os.path.dirname(__file__), "../../server/api")
if _SERVER_API not in sys.path:
    sys.path.insert(0, _SERVER_API)

from models import DJSet, SetTrack  # noqa: E402

from scripts.backfill_set_reliability import (  # noqa: E402
    backfill_reliability,
    backfill_source_url,
)

_n = itertools.count(1)


def _make_set(session, *, tracks=None, commit=True, **fields):
    """Insert a trackid DJSet (+ optional tracks). ``tracks`` = list of is_id bools."""
    i = next(_n)
    dj_set = DJSet(
        title=fields.pop("title", f"Set {i}"),
        source=fields.pop("source", "trackid"),
        **fields,
    )
    session.add(dj_set)
    session.flush()
    for pos, is_id in enumerate(tracks or [], start=1):
        session.add(SetTrack(set_id=dj_set.id, position=pos, is_id=is_id))
    if commit:
        session.commit()
    return dj_set


def _always(value):
    """A placeholder probe stub returning a constant, recording its calls."""
    calls = []

    def probe(set_id):
        calls.append(set_id)
        return value

    probe.calls = calls
    return probe


class TestReliabilityDecision:
    def test_high_id_ratio_is_flagged(self, sync_session):
        s = _make_set(sync_session, tracks=[True, True, True, True, False],
                      source_url="https://trackid.net/audiostream/x")  # 80% ID

        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(False))

        assert stats["scanned"] == 1
        assert stats["to_flag"] == 1 and stats["changed"] == 1
        assert sync_session.get(DJSet, s.id).unreliable is True

    def test_zero_tracks_is_flagged(self, sync_session):
        s = _make_set(sync_session, tracks=[], source_url="https://trackid.net/audiostream/z")

        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(False))

        assert stats["to_flag"] == 1
        assert sync_session.get(DJSet, s.id).unreliable is True

    def test_identified_set_with_source_is_reliable(self, sync_session):
        s = _make_set(sync_session, tracks=[True, False, False, False, False],  # 20% ID
                      source_url="https://trackid.net/audiostream/ok")

        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(True))

        assert stats["changed"] == 0  # already False, stays False
        assert sync_session.get(DJSet, s.id).unreliable is False

    def test_secondary_signal_no_source_no_slug_placeholder(self, sync_session):
        # Low ID ratio but NO source_url, NO slug, placeholder artwork → flagged via
        # the secondary provenance signal.
        s = _make_set(sync_session, tracks=[True, False, False], has_artwork=True)

        probe = _always(True)
        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=probe)

        assert stats["to_flag"] == 1
        assert probe.calls == [s.id]  # the probe WAS consulted (no effective source)
        assert sync_session.get(DJSet, s.id).unreliable is True

    def test_secondary_signal_not_placeholder_stays_reliable(self, sync_session):
        s = _make_set(sync_session, tracks=[True, False, False], has_artwork=True)

        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(False))

        assert stats["changed"] == 0
        assert sync_session.get(DJSet, s.id).unreliable is False

    def test_slug_gives_effective_source_so_placeholder_ignored(self, sync_session):
        # No stored source_url but a slug → effective source_url is recoverable, so
        # the set is NOT provenance-less: the placeholder probe is never consulted
        # and the secondary signal cannot fire.
        s = _make_set(sync_session, tracks=[True, False, False],
                      has_artwork=True, external_slug="my-set-slug")

        probe = _always(True)
        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=probe)

        assert probe.calls == []  # slug short-circuits the read
        assert stats["changed"] == 0
        assert sync_session.get(DJSet, s.id).unreliable is False

    def test_no_artwork_skips_probe(self, sync_session):
        # No effective source AND no stored artwork → nothing to hash, probe skipped.
        s = _make_set(sync_session, tracks=[True, False, False], has_artwork=False)

        probe = _always(True)
        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=probe)

        assert probe.calls == []
        assert stats["changed"] == 0
        assert sync_session.get(DJSet, s.id).unreliable is False


class TestReliabilityRunModes:
    def test_dry_run_mutates_nothing(self, sync_session):
        s = _make_set(sync_session, tracks=[True, True, True],  # 100% ID → would flag
                      source_url="https://trackid.net/audiostream/x")

        stats = backfill_reliability(sync_session, apply=False, placeholder_probe=_always(False))

        assert stats["to_flag"] == 1 and stats["changed"] == 1
        assert sync_session.get(DJSet, s.id).unreliable is False  # untouched

    def test_apply_is_idempotent(self, sync_session):
        _make_set(sync_session, tracks=[True, True, True],
                  source_url="https://trackid.net/audiostream/x")

        first = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(False))
        assert first["changed"] == 1

        second = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(False))
        assert second["changed"] == 0

    def test_non_trackid_sets_are_ignored(self, sync_session):
        # A non-trackid set with zero tracks is NOT scanned (feature is TrackID-scoped).
        s = _make_set(sync_session, tracks=[], source="deezer")

        stats = backfill_reliability(sync_session, apply=True, placeholder_probe=_always(False))

        assert stats["scanned"] == 0
        assert sync_session.get(DJSet, s.id).unreliable is False

    def test_limit_caps_scanned(self, sync_session):
        for _ in range(3):
            _make_set(sync_session, tracks=[True, True, True],
                      source_url="https://trackid.net/audiostream/x")

        stats = backfill_reliability(
            sync_session, apply=True, limit=2, batch_size=1,
            placeholder_probe=_always(False),
        )

        assert stats["scanned"] == 2


class TestProvenanceBonus:
    def test_recovers_source_url_from_slug(self, sync_session):
        s = _make_set(sync_session, tracks=[], external_slug="cool-set", source_url=None)

        stats = backfill_source_url(sync_session, apply=True)

        assert stats["recovered"] == 1
        assert (
            sync_session.get(DJSet, s.id).source_url
            == "https://trackid.net/audiostream/cool-set"
        )

    def test_dry_run_recovers_nothing(self, sync_session):
        s = _make_set(sync_session, tracks=[], external_slug="cool-set", source_url=None)

        stats = backfill_source_url(sync_session, apply=False)

        assert stats["recovered"] == 1
        assert sync_session.get(DJSet, s.id).source_url is None

    def test_skips_sets_with_existing_source_url(self, sync_session):
        s = _make_set(sync_session, tracks=[], external_slug="cool-set",
                      source_url="https://trackid.net/audiostream/kept")

        stats = backfill_source_url(sync_session, apply=True)

        assert stats["recovered"] == 0
        assert sync_session.get(DJSet, s.id).source_url.endswith("/kept")

    def test_skips_sets_without_slug(self, sync_session):
        s = _make_set(sync_session, tracks=[], external_slug=None, source_url=None)

        stats = backfill_source_url(sync_session, apply=True)

        assert stats["recovered"] == 0
        assert sync_session.get(DJSet, s.id).source_url is None

    def test_is_idempotent(self, sync_session):
        _make_set(sync_session, tracks=[], external_slug="cool-set", source_url=None)

        first = backfill_source_url(sync_session, apply=True)
        assert first["recovered"] == 1

        second = backfill_source_url(sync_session, apply=True)
        assert second["recovered"] == 0

    def test_only_touches_trackid_sets(self, sync_session):
        s = _make_set(sync_session, tracks=[], source="deezer",
                      external_slug="x", source_url=None)

        stats = backfill_source_url(sync_session, apply=True)

        assert stats["recovered"] == 0
        assert sync_session.get(DJSet, s.id).source_url is None
