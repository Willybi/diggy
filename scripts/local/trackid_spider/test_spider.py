"""Unit tests for the TrackID spider — NO network, NO prod, mocked HTTP only.

Run standalone (does NOT depend on the main ``tests/`` harness):

    pytest scripts/local/trackid_spider/ -q

Pytest's prepend importmode puts ``scripts/local`` on sys.path (``trackid_spider``
has an ``__init__`` but ``scripts/local`` does not), so the package imports as
``trackid_spider`` even though ``scripts/`` is not a package.
"""

import csv
import json

import httpx
import pytest

from trackid_spider import probe as probe_mod
from trackid_spider import reports as reports_mod
from trackid_spider import spider as spider_mod
from trackid_spider.client import ListingClient, PersistentHTTPError
from trackid_spider.crawl import crawl_window, run_crawl
from trackid_spider.mapping import COLUMNS, map_item
from trackid_spider.store import Store, row_to_export_values
from trackid_spider.windows import (
    Window,
    assert_contiguous,
    build_plan,
    final_pass_window,
    month_boundaries,
    parse_iso,
    plan_from_dict,
    plan_to_dict,
    prescan_monthly,
    to_iso,
)


# --------------------------------------------------------------------------
# Fixtures / fakes
# --------------------------------------------------------------------------
def make_item(_id, **over):
    """A raw listing item resembling the real 2026-08-26 payload."""
    item = {
        "id": _id,
        "slug": f"slug-{_id}",
        "title": f"Set {_id}",
        "channel": f"Chan{_id % 3}",
        "styles": ["Techno"] if _id % 2 else [],
        "status": 2,
        "isDeleted": bool(_id % 5 == 0),
        "trackCount": _id,
        "timeHitRate": 0.5,
        "trackHitRate": 0.25,
        "processingPriority": 1,
        "artworkUrl": f"https://img/{_id}.jpg",
        "addedOn": "2024-01-15T12:00:00Z",
        "createdOn": "2024-01-10T00:00:00Z",
        "addedBy": f"user{_id % 3}",
        "addedById": _id % 3,
        "audioStreamType": 1,
        "externalId": str(1000 + _id),
        "url": f"https://soundcloud.com/x/{_id}",
        "favouriteCount": 0,
        "likeCount": 0,
        "averageRating": None,
    }
    item.update(over)
    return item


class FakeClient:
    """Serves pages from an in-memory item list; records fetched pages."""

    def __init__(self, items, row_count=None, fail=False):
        self.items = items
        self.row_count = row_count if row_count is not None else len(items)
        self.fail = fail
        self.calls = []

    def fetch(self, min_added_on=None, max_added_on=None, page=0, page_size=100):
        self.calls.append(page)
        if self.fail:
            raise PersistentHTTPError("simulated persistent error")
        start = page * page_size
        return self.items[start : start + page_size], self.row_count

    def count(self, min_added_on=None, max_added_on=None, styles=None):
        return self.row_count


class NullLogger:
    def event(self, *a, **k):
        return {}

    def close(self):
        pass


# --------------------------------------------------------------------------
# mapping — payload -> contract, raw_json zero-loss
# --------------------------------------------------------------------------
def test_map_item_contract_columns():
    row = map_item(make_item(42), window_id="W1")
    assert set(row.keys()) == set(COLUMNS)
    assert row["trackid_id"] == 42
    assert row["is_deleted"] == 0  # 42 % 5 != 0
    assert row["audio_stream_type"] == 1
    assert row["status"] == 2
    assert row["window_id"] == "W1"
    # 42 is even so make_item gives styles == []; serialised as a JSON array
    assert json.loads(row["styles"]) == []


def test_map_item_is_deleted_and_styles():
    deleted = map_item(make_item(10), window_id="W")  # 10 % 5 == 0 -> deleted
    assert deleted["is_deleted"] == 1
    styled = map_item(make_item(7), window_id="W")  # odd -> ["Techno"]
    assert json.loads(styled["styles"]) == ["Techno"]


def test_raw_json_captures_unknown_field():
    item = make_item(1, mysteryField={"nested": [1, 2]}, duration="01:31:09")
    row = map_item(item, window_id="W")
    raw = json.loads(row["raw_json"])
    # a field outside the column contract survives verbatim in raw_json
    assert raw["mysteryField"] == {"nested": [1, 2]}
    assert raw["duration"] == "01:31:09"
    assert raw["isDeleted"] is False  # real boolean preserved in raw_json


def test_raw_json_strips_heavy_hydration_keys():
    item = make_item(
        1,
        detectionProcesses=[{"big": "blob"}],
        amendments=[1, 2, 3],
        audioStreamReprocesses={"x": 1},
        isPrivate=True,
    )
    row = map_item(item, window_id="W")
    raw = json.loads(row["raw_json"])
    # the 3 heavy hydration keys are dropped from raw_json (re-fetchable via detail)
    assert "detectionProcesses" not in raw
    assert "amendments" not in raw
    assert "audioStreamReprocesses" not in raw
    # a non-stripped unknown field is STILL preserved verbatim
    assert raw["isPrivate"] is True
    assert raw["id"] == 1


def test_duration_mapped_and_exported(tmp_path):
    # duration is captured verbatim (no parsing) and sits right after track_count
    row = map_item(make_item(1, duration="01:31:09"), window_id="W")
    assert row["duration"] == "01:31:09"
    assert COLUMNS.index("duration") == COLUMNS.index("track_count") + 1
    assert COLUMNS.index("duration") == COLUMNS.index("time_hit_rate") - 1
    # and it round-trips through the staging store into the export at that position
    store = Store(str(tmp_path / "s.db"))
    store.upsert_items([row], now="t")
    exported = list(store.iter_export_rows())[0]
    assert exported["duration"] == "01:31:09"
    assert list(exported.keys()) == list(COLUMNS)
    store.close()


# --------------------------------------------------------------------------
# windows — boundaries, adjacency, adaptive plan, prescan
# --------------------------------------------------------------------------
def test_month_boundaries_contiguous():
    b = month_boundaries(parse_iso("2020-01-10T00:00:00Z"), parse_iso("2020-03-05T00:00:00Z"))
    isos = [to_iso(x) for x in b]
    assert isos[0] == "2020-01-01T00:00:00Z"  # floored to month
    assert "2020-02-01T00:00:00Z" in isos
    assert "2020-03-01T00:00:00Z" in isos
    assert parse_iso(isos[-1]) >= parse_iso("2020-03-05T00:00:00Z")


def _span_count(mn, mx):
    """A count that shrinks with the window span -> bisection terminates."""
    span = (parse_iso(mx) - parse_iso(mn)).total_seconds()
    return int(span / 100_000)  # ~26 for a 30-day month


def test_build_plan_adjacent_no_overlap_no_gap():
    start, end = parse_iso("2020-01-01T00:00:00Z"), parse_iso("2020-04-01T00:00:00Z")
    windows = build_plan(_span_count, start, end, threshold=10)
    assert assert_contiguous(windows) == []  # no boundary gaps/overlaps
    # union covers exactly [start_floored, last_boundary)
    ordered = sorted(windows, key=lambda w: w.min_added_on)
    assert ordered[0].min_added_on == "2020-01-01T00:00:00Z"
    assert ordered[-1].max_added_on == "2020-04-01T00:00:00Z"
    # every window is under threshold unless it hit the 1s floor
    for w in windows:
        span = (parse_iso(w.max_added_on) - parse_iso(w.min_added_on)).total_seconds()
        assert w.expected_count <= 10 or span <= 1


def test_build_plan_small_counts_one_window_per_month():
    start, end = parse_iso("2020-01-01T00:00:00Z"), parse_iso("2020-03-01T00:00:00Z")
    windows = build_plan(lambda mn, mx: 3, start, end, threshold=10)
    assert len(windows) == 2  # two months, each under threshold
    assert assert_contiguous(windows) == []


def test_prescan_monthly():
    start, end = parse_iso("2020-01-01T00:00:00Z"), parse_iso("2020-03-01T00:00:00Z")
    rows = prescan_monthly(lambda mn, mx: 7, start, end)
    assert [c for _lo, _hi, c in rows] == [7, 7]
    assert rows[0][0] == "2020-01-01T00:00:00Z"


def test_plan_roundtrip():
    ws = [Window("a", "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z", 5)]
    doc = plan_to_dict(ws, threshold=10, start="2020-01-01T00:00:00Z", end="2020-02-01T00:00:00Z")
    back = plan_from_dict(doc)
    assert back[0] == ws[0]
    assert doc["total_expected"] == 5


def test_final_pass_window():
    fw = final_pass_window("2024-01-01T00:00:00Z", now=parse_iso("2024-01-02T00:00:00Z"))
    assert fw.min_added_on == "2024-01-01T00:00:00Z"
    assert fw.max_added_on == "2024-01-02T00:00:00Z"
    assert fw.window_id.startswith("final__")


# --------------------------------------------------------------------------
# store — upsert idempotency, checkpoint, export ordering
# --------------------------------------------------------------------------
def test_upsert_dedups_on_trackid_id(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    rows = [map_item(make_item(i), "W") for i in range(1, 6)]
    store.upsert_items(rows, now="t0")
    store.upsert_items(rows, now="t1")  # same ids again
    assert store.staging_count() == 5  # no duplicates
    # a changed field is updated in place, first_seen_at preserved
    updated = map_item(make_item(1, title="NEW"), "W2")
    store.upsert_items([updated], now="t2")
    assert store.staging_count() == 5
    got = store.conn.execute(
        "SELECT title, window_id, first_seen_at, last_seen_at "
        "FROM trackid_index_staging WHERE trackid_id=1"
    ).fetchone()
    assert got["title"] == "NEW"
    assert got["window_id"] == "W2"
    assert got["first_seen_at"] == "t0"  # preserved
    assert got["last_seen_at"] == "t2"  # advanced
    store.close()


def test_load_plan_idempotent_preserves_progress(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    w = Window("w1", "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z", 100)
    store.load_plan([w], now="t0")
    store.update_window("w1", "t1", pages_done=3, state="in_progress")
    store.load_plan([w], now="t2")  # re-load same plan
    row = store.get_window("w1")
    assert row["pages_done"] == 3  # progress not rewound
    assert row["state"] == "in_progress"
    store.close()


def test_export_rows_in_contract_order(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.upsert_items([map_item(make_item(3), "W"), map_item(make_item(1), "W")], now="t")
    rows = list(store.iter_export_rows())
    assert [r["trackid_id"] for r in rows] == [1, 3]  # ordered by id
    assert list(rows[0].keys()) == list(COLUMNS)  # exact contract order
    store.close()


# --------------------------------------------------------------------------
# client — backoff / retry policy (mocked transport, injected sleep+clock)
# --------------------------------------------------------------------------
def _client_with(handler, sleeps):
    clock = {"t": 0.0}

    def fake_sleep(s):
        sleeps.append(s)
        clock["t"] += s

    def mono():
        clock["t"] += 0.001
        return clock["t"]

    return ListingClient(
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        monotonic=mono,
        max_retries=3,
    )


def test_client_retries_then_succeeds():
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] < 3:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"result": {"audiostreams": [make_item(1)], "rowCount": 1}})

    sleeps = []
    client = _client_with(handler, sleeps)
    items, count = client.fetch(page=0)
    assert count == 1 and len(items) == 1
    assert len(sleeps) >= 2  # backed off twice before success


def test_client_persistent_error_after_retries():
    def handler(request):
        return httpx.Response(500, json={})

    client = _client_with(handler, [])
    with pytest.raises(PersistentHTTPError):
        client.fetch(page=0)


def test_client_non_retryable_4xx_immediate():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={})

    client = _client_with(handler, [])
    with pytest.raises(PersistentHTTPError):
        client.fetch(page=0)
    assert calls["n"] == 1  # not retried


def test_client_count_uses_pagesize_1():
    seen = {}

    def handler(request):
        seen["pageSize"] = request.url.params.get("pageSize")
        return httpx.Response(200, json={"result": {"audiostreams": [], "rowCount": 4242}})

    client = _client_with(handler, [])
    assert client.count("2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z") == 4242
    assert seen["pageSize"] == "1"


# --------------------------------------------------------------------------
# crawl — nominal, empty, overflow, resume, failed
# --------------------------------------------------------------------------
def _seed_window(store, wid="w", expected=None, count_items=5, pages_done=0):
    w = Window(wid, "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", expected)
    store.load_plan([w], now="t0")
    if pages_done:
        store.update_window(wid, "t0", pages_done=pages_done)
    return store.get_window(wid)


def test_crawl_window_nominal(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    client = FakeClient([make_item(i) for i in range(1, 6)])
    row = _seed_window(store, expected=5, count_items=5)
    agg = crawl_window(store, client, row, NullLogger(), page_size=2)
    assert agg["items"] == 5
    assert store.staging_count() == 5
    assert store.get_window("w")["state"] == "done"
    store.close()


def test_crawl_window_empty(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    client = FakeClient([], row_count=0)
    row = _seed_window(store, expected=0)
    agg = crawl_window(store, client, row, NullLogger(), page_size=2)
    assert agg["items"] == 0
    assert store.staging_count() == 0
    assert store.get_window("w")["state"] == "done"
    store.close()


def test_crawl_window_overflow_flagged(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    # plan expected 2 but the window actually has 5 -> overflow, still fully crawled
    client = FakeClient([make_item(i) for i in range(1, 6)], row_count=5)
    row = _seed_window(store, expected=2)
    crawl_window(store, client, row, NullLogger(), page_size=2)
    w = store.get_window("w")
    assert w["state"] == "overflow"
    assert w["overflow"] == 1
    assert store.staging_count() == 5  # no data lost despite the under-count
    store.close()


def test_crawl_window_resume_from_pages_done(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    items = [make_item(i) for i in range(1, 6)]
    # simulate a crash after page 0 (2 items) was imported: pre-import + pages_done=1
    store.upsert_items([map_item(items[0], "w"), map_item(items[1], "w")], now="t0")
    client = FakeClient(items)
    row = _seed_window(store, expected=5, pages_done=1)
    crawl_window(store, client, row, NullLogger(), page_size=2)
    # resumed at page 1, NEVER re-fetched page 0
    assert client.calls[0] == 1
    assert 0 not in client.calls
    assert store.staging_count() == 5  # complete, no gap, no dup
    store.close()


def test_crawl_window_idempotent_second_run(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    items = [make_item(i) for i in range(1, 6)]
    row = _seed_window(store, expected=5)
    crawl_window(store, FakeClient(items), row, NullLogger(), page_size=2)
    n1 = store.staging_count()
    # re-run the whole window from scratch -> upsert dedups, count unchanged
    store.update_window("w", "t", pages_done=0, state="pending")
    crawl_window(store, FakeClient(items), store.get_window("w"), NullLogger(), page_size=2)
    assert store.staging_count() == n1 == 5
    store.close()


def test_crawl_window_failed_after_persistent_error(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    client = FakeClient([make_item(1)], fail=True)
    row = _seed_window(store, expected=1)
    crawl_window(store, client, row, NullLogger(), page_size=2)
    w = store.get_window("w")
    assert w["state"] == "failed"
    assert "persistent" in (w["error"] or "")
    assert store.staging_count() == 0
    store.close()


def test_run_crawl_full_with_final_pass(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    plan = [Window("w1", "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", 3)]
    client = FakeClient([make_item(i) for i in range(1, 4)], row_count=3)
    summary = run_crawl(store, client, plan, NullLogger(), page_size=2, final_pass=True)
    assert summary["staging_rows"] == 3
    # final pass window was created and processed
    assert any(k.startswith("final__") for k in
               [r["window_id"] for r in store.conn.execute(
                   "SELECT window_id FROM crawl_windows").fetchall()])
    store.close()


class BoundedFailClient:
    """Always raises PersistentHTTPError; ABORTS (not hangs) if fetched more than
    ``limit`` times — so a re-selection busy-loop fails the test instead of
    spinning forever."""

    def __init__(self, limit=20):
        self.calls = []
        self.limit = limit

    def fetch(self, min_added_on=None, max_added_on=None, page=0, page_size=100):
        self.calls.append(page)
        if len(self.calls) > self.limit:
            raise AssertionError(
                "run_crawl did not terminate — a failed window was re-selected"
            )
        raise PersistentHTTPError("simulated persistent error")

    def count(self, *a, **k):
        return 0


def test_windows_to_crawl_excludes_failed_and_final(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.load_plan(
        [
            Window("w_pending", "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", 1),
            Window("w_failed", "2024-02-01T00:00:00Z", "2024-03-01T00:00:00Z", 1),
            Window("final__x", "2024-03-01T00:00:00Z", "2024-04-01T00:00:00Z", 1),
        ],
        now="t0",
    )
    store.update_window("w_failed", "t1", state="failed")
    ids = [r["window_id"] for r in store.windows_to_crawl()]
    assert ids == ["w_pending"]  # failed + final-pass windows both excluded
    store.close()


def test_reset_failed_windows_preserves_pages_done(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.load_plan(
        [Window("w1", "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", 5)], now="t0"
    )
    store.update_window("w1", "t1", pages_done=4, state="failed")
    store.reset_failed_windows("t2")
    row = store.get_window("w1")
    assert row["state"] == "pending"
    assert row["pages_done"] == 4  # only state flipped, progress kept
    assert [r["window_id"] for r in store.windows_to_crawl()] == ["w1"]
    store.close()


def test_run_crawl_terminates_on_persistent_failure_then_retries_next_run(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    plan = [Window("w1", "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", 3)]

    # First run: the window fails persistently. run_crawl must TERMINATE (the
    # BoundedFailClient aborts the test if it busy-loops re-selecting the window).
    fail_client = BoundedFailClient(limit=20)
    run_crawl(store, fail_client, plan, NullLogger(), page_size=2, final_pass=False)
    assert store.get_window("w1")["state"] == "failed"
    assert len(fail_client.calls) <= 20  # bounded, not an infinite loop

    # Second run: reset_failed_windows flips it back to pending, then it succeeds.
    good_client = FakeClient([make_item(i) for i in range(1, 4)], row_count=3)
    run_crawl(store, good_client, plan, NullLogger(), page_size=2, final_pass=False)
    assert store.get_window("w1")["state"] == "done"
    assert store.staging_count() == 3
    store.close()


# --------------------------------------------------------------------------
# probe — pure decision helpers
# --------------------------------------------------------------------------
def test_check_windowing_clean_partition():
    res = probe_mod.check_windowing([1, 2, 3, 4], [3, 4], [1, 2])
    assert res["ok"] is True
    assert res["overlap"] == [] and res["missing"] == []


def test_check_windowing_detects_overlap_and_loss():
    res = probe_mod.check_windowing([1, 2, 3, 4, 5], [2, 3], [3, 4])
    assert 3 in res["overlap"]  # 3 in both halves
    assert 5 in res["missing"]  # 5 in whole, in neither half
    assert res["ok"] is False


def test_check_pagesize_ceiling():
    res = probe_mod.check_pagesize_ceiling({20: 20, 50: 50, 100: 100, 200: 100})
    assert res["ceiling"] == 100


def test_check_pagination_stable():
    assert probe_mod.check_pagination_stable([1, 2, 3], [1, 2, 3]) is True
    assert probe_mod.check_pagination_stable([1, 2, 3], [1, 3, 2]) is False


def test_interpret_v5_included():
    res = probe_mod.interpret_v5(enumerated_count=100, row_count=100, deleted_seen=4)
    assert res["deleted_included_in_rowcount"] is True
    res2 = probe_mod.interpret_v5(enumerated_count=96, row_count=100, deleted_seen=4)
    assert res2["deleted_included_in_rowcount"] is False


# --------------------------------------------------------------------------
# reports — completeness + volumetry
# --------------------------------------------------------------------------
def test_completeness_report(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.load_plan([Window("w", "2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z", 5)], now="t")
    store.upsert_items([map_item(make_item(i), "w") for i in range(1, 6)], now="t")
    report, text = reports_mod.completeness_report(store, total_known=5, deleted_in_rowcount=True)
    assert report["staging_rows"] == 5
    assert report["sum_expected_windows"] == 5
    assert report["id_range_span"] == 5  # ids 1..5 dense
    assert "COMPLETENESS" in text
    store.close()


def test_volumetry_report(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.upsert_items([map_item(make_item(i), "w") for i in range(1, 21)], now="t")
    report, text = reports_mod.volumetry_report(store, top_n=3, spike_min=1)
    assert report["staging_rows"] == 20
    assert report["deleted_rows"] == store.deleted_count()
    assert len(report["track_hit_rate_histogram"]) == 10
    assert "VOLUMETRY" in text
    store.close()


# --------------------------------------------------------------------------
# export — CSV + NDJSON serialisation (via the spider helper)
# --------------------------------------------------------------------------
def test_export_csv_column_contract(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.upsert_items([map_item(make_item(1), "W")], now="t")
    out = tmp_path / "out.csv"
    n = spider_mod._export(store, str(out), "csv")
    assert n == 1
    with open(out, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        first = next(reader)
    assert header == list(COLUMNS)  # exact order
    rec = dict(zip(header, first))
    assert rec["trackid_id"] == "1"
    assert json.loads(rec["styles"]) == ["Techno"]  # styles serialised as JSON
    assert json.loads(rec["raw_json"])["id"] == 1  # raw_json is valid JSON
    store.close()


def test_export_ndjson_column_contract(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    store.upsert_items([map_item(make_item(2), "W"), map_item(make_item(1), "W")], now="t")
    out = tmp_path / "out.ndjson"
    n = spider_mod._export(store, str(out), "ndjson")
    assert n == 2
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    first = json.loads(lines[0])
    assert list(first.keys()) == list(COLUMNS)  # contract order preserved
    assert first["trackid_id"] == 1  # ordered by id
    # styles/raw_json carried as JSON strings (contract), raw_json re-parseable
    assert json.loads(first["raw_json"])["slug"] == "slug-1"


def test_row_to_export_values_none_becomes_empty():
    row = {c: None for c in COLUMNS}
    row["trackid_id"] = 7
    vals = row_to_export_values(row)
    assert vals[0] == "7"
    assert vals[COLUMNS.index("average_rating")] == ""  # None -> empty string
