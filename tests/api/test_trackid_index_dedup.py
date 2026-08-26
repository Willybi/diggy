"""Unit tests for the PURE TrackID index dedup pre-grouping (C11 / L3).

DB-free: exercises ``cluster_index`` (and its duration guard) directly with
in-memory tuples. No PG fixture, no SQLite engine — the function is pure Python.
Importing the OPS script is side-effect-free (a lazy engine, no connection).
"""
from scripts.import_trackid_index import _duration_compatible, cluster_index

CH = "Boiler Room"  # a shared channel for the "same block" cases


def _grouped(mapping, a, b):
    """True iff a and b landed in the SAME non-null cluster."""
    return a in mapping and b in mapping and mapping[a] == mapping[b]


def test_same_channel_identical_base_title_groups():
    rows = [
        (1, "Deep House Mix", CH, "01:00:00"),
        (2, "Deep House Mix", CH, "01:00:20"),  # within 2% -> compatible
    ]
    mapping = cluster_index(rows)
    assert _grouped(mapping, 1, 2)


def test_token_reorder_ratio_one_groups():
    # Same token set, different order -> base_title strings differ but
    # token_set_ratio == 1.0 (>= 0.95) -> grouped.
    rows = [
        (10, "Sunset Session Ibiza", CH, "02:00:00"),
        (11, "Ibiza Sunset Session", CH, "02:00:30"),
    ]
    mapping = cluster_index(rows)
    assert _grouped(mapping, 10, 11)


def test_different_channel_never_groups():
    rows = [
        (20, "Deep House Mix", "Channel A", "01:00:00"),
        (21, "Deep House Mix", "Channel B", "01:00:00"),
    ]
    mapping = cluster_index(rows)
    assert not _grouped(mapping, 20, 21)
    assert mapping == {}  # both singletons within their own channel block


def test_low_ratio_does_not_group():
    # {ibiza,session,sunset} vs {session,sunset} -> Jaccard 2/3 < 0.95, short
    # titles so no fuzzy neighbourhood -> NOT grouped.
    rows = [
        (30, "Sunset Session Ibiza", CH, "01:00:00"),
        (31, "Sunset Session", CH, "01:00:00"),
    ]
    mapping = cluster_index(rows)
    assert not _grouped(mapping, 30, 31)


def test_duration_guard_blocks_far_durations():
    # Identical base_title, same channel, but 1h vs 2h (both known) -> > 2% -> blocked.
    rows = [
        (40, "Warehouse Set", CH, "01:00:00"),
        (41, "Warehouse Set", CH, "02:00:00"),
    ]
    mapping = cluster_index(rows)
    assert not _grouped(mapping, 40, 41)
    assert mapping == {}


def test_unknown_duration_does_not_block():
    # Identical base_title, one duration unknown -> guard is permissive -> grouped.
    rows = [
        (50, "Warehouse Set", CH, "01:00:00"),
        (51, "Warehouse Set", CH, None),
    ]
    mapping = cluster_index(rows)
    assert _grouped(mapping, 50, 51)


def test_singleton_has_no_group():
    rows = [(60, "A Lonely Set", CH, "01:00:00")]
    mapping = cluster_index(rows)
    assert mapping == {}


def test_three_members_one_cluster():
    rows = [
        (70, "Techno Marathon", CH, "03:00:00"),
        (71, "Techno Marathon", CH, "03:01:00"),  # within 2% of 70
        (72, "Techno Marathon", CH, "03:02:00"),  # within 2% of 71 (chains in)
    ]
    mapping = cluster_index(rows)
    assert _grouped(mapping, 70, 71)
    assert _grouped(mapping, 71, 72)
    assert len(set(mapping.values())) == 1  # exactly one cluster


def test_duration_guard_relative_tolerance():
    hour = 3_600_000
    assert _duration_compatible(hour, hour) is True
    assert _duration_compatible(hour, int(hour * 1.01)) is True  # 1% <= 2%
    assert _duration_compatible(hour, int(hour * 1.05)) is False  # 5% > 2%
    assert _duration_compatible(hour, None) is True  # unknown never blocks
    assert _duration_compatible(None, None) is True
