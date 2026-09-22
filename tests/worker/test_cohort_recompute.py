"""Tests for the derived artist-cohort recompute (workers/cohort, C14.a — L1).

Exercises the pure ``compute_tier`` and the session-level ``recompute_cohort``
against a real sync SQLite session (the shared ``sync_session`` fixture). Asserts
the tier thresholds, the signal wiring (lib / likes / reliable-root-recent DJ
sets / catalog depth / follows), auto-promotion, pure-signal pruning and the
preservation of admin overrides. Same import/path pattern as the sibling worker
tests (e.g. test_backfill_completion_pct.py).
"""
import itertools
import os
import sys
from datetime import date, datetime, timedelta, timezone

# Make server + server/api importable (workers.* lives under server/, models
# under server/api/).
_SERVER = os.path.join(os.path.dirname(__file__), "../../server")
_SERVER_API = os.path.join(os.path.dirname(__file__), "../../server/api")
for _p in (_SERVER, _SERVER_API):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from models import (  # noqa: E402
    Artist,
    ArtistCohort,
    CatalogArtist,
    CatalogEntry,
    DJSet,
    FollowedArtist,
    SetArtist,
    User,
    UserOpinion,
    UserTrack,
)

from workers.cohort import (  # noqa: E402
    compute_tier,
    recompute_cohort,
    select_due_cohort_ids,
)

# Fixed "now" so the 12-month window is deterministic across runs.
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
RECENT = date(2026, 6, 1)  # within 12 months of NOW
OLD = date(2024, 1, 1)  # > 12 months before NOW

_n = itertools.count(1)


# ── builders ─────────────────────────────────────────────────────────────────
def _artist(session, name=None):
    i = next(_n)
    a = Artist(name=name or f"Artist {i}", normalized_name=f"artist-{i}")
    session.add(a)
    session.flush()
    return a


def _user(session):
    i = next(_n)
    u = User(email=f"u{i}@x.io", username=f"u{i}", google_id=f"g{i}")
    session.add(u)
    session.flush()
    return u


def _catalog(session):
    i = next(_n)
    c = CatalogEntry(title=f"Track {i}", artist="X", normalized_key=f"track-{i}")
    session.add(c)
    session.flush()
    return c


def _own(session, artist, catalog):
    session.add(CatalogArtist(catalog_id=catalog.id, artist_id=artist.id))
    session.flush()


def _in_lib(session, user, catalog):
    session.add(UserTrack(user_id=user.id, catalog_id=catalog.id))
    session.flush()


def _catalog_tracks(session, artist, n):
    """Give ``artist`` ``n`` distinct catalog tracks (nb_catalog signal)."""
    cats = []
    for _ in range(n):
        c = _catalog(session)
        _own(session, artist, c)
        cats.append(c)
    return cats


def _dj_set(session, **fields):
    i = next(_n)
    s = DJSet(
        title=fields.pop("title", f"Set {i}"),
        source=fields.pop("source", "trackid"),
        **fields,
    )
    session.add(s)
    session.flush()
    return s


def _dj(session, artist, dj_set, role="dj"):
    session.add(SetArtist(set_id=dj_set.id, artist_id=artist.id, role=role))
    session.flush()


def _reliable_set(session, artist, **fields):
    """A reliable, root, non-virtual, recent set featuring ``artist`` as DJ."""
    fields.setdefault("event_date", RECENT)
    fields.setdefault("is_virtual", False)
    fields.setdefault("unreliable", False)
    s = _dj_set(session, **fields)
    _dj(session, artist, s)
    return s


def _like_artist(session, user, artist):
    session.add(
        UserOpinion(
            user_id=user.id,
            entity_type="artist",
            entity_key=str(artist.id),
            opinion="liked",
        )
    )
    session.flush()


def _like_track(session, user, catalog):
    session.add(
        UserOpinion(
            user_id=user.id,
            entity_type="track",
            entity_key=str(catalog.id),
            opinion="liked",
        )
    )
    session.flush()


def _cohort(session, artist_id):
    return session.get(ArtistCohort, artist_id)


def _seed_cohort(session, artist, *, tier, last_checked_at=None, excluded=False):
    """Seed an artist_cohort row directly (for the select_due_cohort_ids tests —
    they exercise the due/order logic, not the recompute that would build them)."""
    row = ArtistCohort(
        artist_id=artist.id,
        tier=tier,
        computed_tier=tier,
        excluded=excluded,
        last_checked_at=last_checked_at,
    )
    session.add(row)
    session.flush()
    return row


# ── compute_tier (pure thresholds) ───────────────────────────────────────────
class TestComputeTier:
    def test_library_membership_makes_t1(self):
        assert compute_tier(
            nb_lib=1, nb_likes=0, nb_sets_12m=0, nb_catalog=0, followed=False
        ) == 1

    def test_followed_makes_t1(self):
        assert compute_tier(
            nb_lib=0, nb_likes=0, nb_sets_12m=0, nb_catalog=0, followed=True
        ) == 1

    def test_likes_make_t1(self):
        assert compute_tier(
            nb_lib=0, nb_likes=2, nb_sets_12m=0, nb_catalog=0, followed=False
        ) == 1

    def test_three_sets_make_t1(self):
        assert compute_tier(
            nb_lib=0, nb_likes=0, nb_sets_12m=3, nb_catalog=1, followed=False
        ) == 1

    def test_two_sets_with_deep_catalog_make_t1(self):
        assert compute_tier(
            nb_lib=0, nb_likes=0, nb_sets_12m=2, nb_catalog=10, followed=False
        ) == 1

    def test_two_sets_shallow_catalog_falls_to_t2(self):
        # 2 sets is below SETS_12M_T1 (3) and the catalog isn't deep, so no T1;
        # but 2 sets >= SETS_12M_T2 (1) → T2.
        assert compute_tier(
            nb_lib=0, nb_likes=0, nb_sets_12m=2, nb_catalog=5, followed=False
        ) == 2

    def test_deep_catalog_only_is_t2(self):
        assert compute_tier(
            nb_lib=0, nb_likes=0, nb_sets_12m=0, nb_catalog=10, followed=False
        ) == 2

    def test_one_set_is_t2(self):
        assert compute_tier(
            nb_lib=0, nb_likes=0, nb_sets_12m=1, nb_catalog=0, followed=False
        ) == 2

    def test_shallow_catalog_only_out_of_cohort(self):
        assert (
            compute_tier(
                nb_lib=0, nb_likes=0, nb_sets_12m=0, nb_catalog=9, followed=False
            )
            is None
        )

    def test_no_signals_out_of_cohort(self):
        assert (
            compute_tier(
                nb_lib=0, nb_likes=0, nb_sets_12m=0, nb_catalog=0, followed=False
            )
            is None
        )


# ── recompute_cohort (end-to-end over a session) ─────────────────────────────
class TestRecomputeCohort:
    def test_library_artist_enters_daily(self, sync_session):
        a = _artist(sync_session)
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        _in_lib(sync_session, _user(sync_session), c)

        stats = recompute_cohort(sync_session, now=NOW)

        row = _cohort(sync_session, a.id)
        assert row is not None
        assert row.tier == 1 and row.computed_tier == 1
        assert row.signals["nb_lib"] == 1 and row.signals["followed"] is False
        assert row.last_recomputed_at is not None
        assert stats["n_t1"] == 1 and stats["n_total"] == 1

    def test_shallow_catalog_artist_not_in_cohort(self, sync_session):
        a = _artist(sync_session)
        _catalog_tracks(sync_session, a, 3)  # < CATALOG_T2, nothing else

        recompute_cohort(sync_session, now=NOW)

        assert _cohort(sync_session, a.id) is None

    def test_deep_catalog_artist_is_t2(self, sync_session):
        a = _artist(sync_session)
        _catalog_tracks(sync_session, a, 10)

        stats = recompute_cohort(sync_session, now=NOW)

        row = _cohort(sync_session, a.id)
        assert row.tier == 2 and row.computed_tier == 2
        assert row.signals["nb_catalog"] == 10
        assert stats["n_t2"] == 1

    def test_followed_artist_is_member_without_other_signal(self, sync_session):
        a = _artist(sync_session)
        session_user = _user(sync_session)
        sync_session.add(FollowedArtist(user_id=session_user.id, artist_id=a.id))
        sync_session.flush()

        recompute_cohort(sync_session, now=NOW)

        row = _cohort(sync_session, a.id)
        assert row.tier == 1 and row.signals["followed"] is True

    def test_artist_like_makes_t1(self, sync_session):
        a = _artist(sync_session)
        _like_artist(sync_session, _user(sync_session), a)

        recompute_cohort(sync_session, now=NOW)

        row = _cohort(sync_session, a.id)
        assert row.tier == 1 and row.signals["nb_likes"] == 1

    def test_track_like_via_catalog_artists_makes_t1(self, sync_session):
        a = _artist(sync_session)
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        _like_track(sync_session, _user(sync_session), c)

        recompute_cohort(sync_session, now=NOW)

        row = _cohort(sync_session, a.id)
        assert row.tier == 1 and row.signals["nb_likes"] == 1

    def test_sets_count_only_reliable_root_recent(self, sync_session):
        a = _artist(sync_session)
        # 3 that must count: reliable recent (event_date), + one that falls back
        # to played_date, + a plain reliable recent one.
        _reliable_set(sync_session, a)
        _reliable_set(sync_session, a, event_date=None, played_date=RECENT)
        _reliable_set(sync_session, a)
        # Excluded ones: unreliable, virtual, old (> 12 months), and a non-dj role.
        _reliable_set(sync_session, a, unreliable=True)
        _reliable_set(sync_session, a, is_virtual=True)
        _reliable_set(sync_session, a, event_date=OLD)
        _reliable_set(sync_session, a, event_date=None, played_date=OLD)
        guest = _dj_set(sync_session, event_date=RECENT)
        _dj(sync_session, a, guest, role="guest")  # role != 'dj' → ignored

        recompute_cohort(sync_session, now=NOW)

        row = _cohort(sync_session, a.id)
        assert row.signals["nb_sets_12m"] == 3
        assert row.tier == 1  # 3 sets → T1

    def test_child_set_excluded_roots_only(self, sync_session):
        a = _artist(sync_session)
        parent = _dj_set(sync_session, event_date=RECENT)
        # A non-root set (parent_set_id set) must not count, even if reliable.
        _reliable_set(sync_session, a, parent_set_id=parent.id)

        recompute_cohort(sync_session, now=NOW)

        assert _cohort(sync_session, a.id) is None

    def test_auto_promotion_on_second_run(self, sync_session):
        a = _artist(sync_session)
        _catalog_tracks(sync_session, a, 3)  # shallow → not in cohort yet

        recompute_cohort(sync_session, now=NOW)
        assert _cohort(sync_session, a.id) is None

        # Cross a threshold: one of the tracks lands in a user's library.
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        _in_lib(sync_session, _user(sync_session), c)

        recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        assert row is not None and row.tier == 1

    def test_pure_signal_dropout_is_pruned(self, sync_session):
        a = _artist(sync_session)
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        ut = UserTrack(user_id=_user(sync_session).id, catalog_id=c.id)
        sync_session.add(ut)
        sync_session.flush()

        recompute_cohort(sync_session, now=NOW)
        assert _cohort(sync_session, a.id) is not None

        # Remove the only signal → the row must be deleted (dropout).
        sync_session.delete(ut)
        sync_session.flush()

        stats = recompute_cohort(sync_session, now=NOW)
        assert _cohort(sync_session, a.id) is None
        assert stats["n_pruned"] == 1

    def test_overrides_preserved_and_not_overwritten(self, sync_session):
        a = _artist(sync_session)
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        _in_lib(sync_session, _user(sync_session), c)  # computes to T1

        recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        # Admin forces T2 + pins.
        row.forced_tier = 2
        row.pinned = True
        sync_session.flush()

        recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        assert row.forced_tier == 2 and row.pinned is True
        assert row.computed_tier == 1  # signals still say T1
        assert row.tier == 2  # forced_tier wins for the effective tier

    def test_excluded_row_kept_on_dropout(self, sync_session):
        a = _artist(sync_session)
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        ut = UserTrack(user_id=_user(sync_session).id, catalog_id=c.id)
        sync_session.add(ut)
        sync_session.flush()

        recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        row.excluded = True
        prior_tier = row.tier
        sync_session.flush()

        # Artist goes silent, but the exclusion must survive.
        sync_session.delete(ut)
        sync_session.flush()

        stats = recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        assert row is not None  # not pruned
        assert row.excluded is True
        assert row.computed_tier is None  # no longer qualifies
        assert row.tier == prior_tier  # kept for memory of the exclusion
        assert stats["n_pruned"] == 0 and stats["n_excluded"] == 1

    def test_forced_tier_kept_alive_on_dropout(self, sync_session):
        a = _artist(sync_session)
        c = _catalog(sync_session)
        _own(sync_session, a, c)
        ut = UserTrack(user_id=_user(sync_session).id, catalog_id=c.id)
        sync_session.add(ut)
        sync_session.flush()

        recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        row.forced_tier = 2
        sync_session.flush()

        sync_session.delete(ut)
        sync_session.flush()

        recompute_cohort(sync_session, now=NOW)
        row = _cohort(sync_session, a.id)
        assert row is not None and row.computed_tier is None
        assert row.forced_tier == 2 and row.tier == 2

    def test_stats_shape(self, sync_session):
        stats = recompute_cohort(sync_session, now=NOW)
        assert set(stats) == {
            "n_t1",
            "n_t2",
            "n_pinned",
            "n_excluded",
            "n_pruned",
            "n_total",
        }
        assert all(v == 0 for v in stats.values())


# ── select_due_cohort_ids (release-watch worklist, L2) ───────────────────────
class TestSelectDueCohortIds:
    def test_t1_due_before_t2_due(self, sync_session):
        # Created T2 first to prove the order is by tier, not insertion.
        t2 = _artist(sync_session)
        t1 = _artist(sync_session)
        _seed_cohort(sync_session, t2, tier=2)  # never checked → due
        _seed_cohort(sync_session, t1, tier=1)  # never checked → due

        assert select_due_cohort_ids(sync_session, NOW, budget=10) == [
            t1.id,
            t2.id,
        ]

    def test_budget_caps_the_result_keeping_t1(self, sync_session):
        a = _artist(sync_session)
        b = _artist(sync_session)
        c = _artist(sync_session)
        _seed_cohort(sync_session, a, tier=1)
        _seed_cohort(sync_session, b, tier=1)
        _seed_cohort(sync_session, c, tier=2)

        ids = select_due_cohort_ids(sync_session, NOW, budget=2)

        assert len(ids) == 2
        # The two T1s are kept (higher priority); the T2 is dropped by the cap.
        assert set(ids) == {a.id, b.id}

    def test_never_checked_before_recently_checked(self, sync_session):
        never = _artist(sync_session)
        old = _artist(sync_session)
        _seed_cohort(
            sync_session, old, tier=1, last_checked_at=NOW - timedelta(days=3)
        )
        _seed_cohort(sync_session, never, tier=1, last_checked_at=None)

        # NULLS FIRST: the never-checked member is the highest priority.
        assert select_due_cohort_ids(sync_session, NOW, budget=10) == [
            never.id,
            old.id,
        ]

    def test_oldest_check_first_within_tier(self, sync_session):
        newer = _artist(sync_session)
        older = _artist(sync_session)
        _seed_cohort(
            sync_session, newer, tier=1, last_checked_at=NOW - timedelta(days=2)
        )
        _seed_cohort(
            sync_session, older, tier=1, last_checked_at=NOW - timedelta(days=10)
        )

        # last_checked_at ASC → the member checked longest ago comes first.
        assert select_due_cohort_ids(sync_session, NOW, budget=10) == [
            older.id,
            newer.id,
        ]

    def test_cadence_filters_out_fresh_members(self, sync_session):
        t1_due = _artist(sync_session)
        t1_fresh = _artist(sync_session)
        t2_due = _artist(sync_session)
        t2_fresh = _artist(sync_session)
        # T1 cadence 1 day: 2 days ago → due, 2 hours ago → not due.
        _seed_cohort(
            sync_session, t1_due, tier=1, last_checked_at=NOW - timedelta(days=2)
        )
        _seed_cohort(
            sync_session, t1_fresh, tier=1, last_checked_at=NOW - timedelta(hours=2)
        )
        # T2 cadence 7 days: 8 days ago → due, 3 days ago → not due.
        _seed_cohort(
            sync_session, t2_due, tier=2, last_checked_at=NOW - timedelta(days=8)
        )
        _seed_cohort(
            sync_session, t2_fresh, tier=2, last_checked_at=NOW - timedelta(days=3)
        )

        ids = select_due_cohort_ids(sync_session, NOW, budget=10)

        assert ids == [t1_due.id, t2_due.id]  # fresh members filtered, T1 first

    def test_excluded_never_selected(self, sync_session):
        a = _artist(sync_session)
        _seed_cohort(sync_session, a, tier=1, excluded=True)  # due but excluded

        assert select_due_cohort_ids(sync_session, NOW, budget=10) == []

    def test_tier3_never_drawn(self, sync_session):
        a = _artist(sync_session)
        _seed_cohort(sync_session, a, tier=3)  # never checked, but T3 is deferred

        assert select_due_cohort_ids(sync_session, NOW, budget=10) == []

    def test_empty_when_nothing_due(self, sync_session):
        a = _artist(sync_session)
        _seed_cohort(
            sync_session, a, tier=1, last_checked_at=NOW - timedelta(hours=1)
        )

        assert select_due_cohort_ids(sync_session, NOW, budget=10) == []
