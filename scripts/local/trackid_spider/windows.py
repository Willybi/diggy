"""Static window plan model + adaptive time-window builder.

The listing is enumerated by fencing on ``addedOn`` with ``minAddedOn`` /
``maxAddedOn`` (half-open ``[min, max)`` — confirmed exclusive on ``max`` against
the real API). Windowing by ``addedOn`` is what makes deep pagination STABLE: a
window whose ``max <= run_start`` can never gain a new item mid-crawl (a new item
has ``addedOn = now > max``), so page offsets don't shift under us. The final pass
``[run_start, now)`` mops up anything added during the crawl.

Adjacent windows share a boundary (``w[i].max == w[i+1].min``) so the plan has NO
gap; the ``[min, max)`` half-open semantics mean NO overlap either. Even if the
boundary were inclusive on both ends, the staging upsert (PK = trackid_id) makes
a one-item overlap lossless — separation-by-design plus idempotent upsert.

The plan is STATIC and auditable: a JSON list of ``{window_id, min, max,
expected_count}``. It is built by an adaptive time bisection — start monthly, and
recursively halve any window whose cheap rowCount probe exceeds the threshold
(~10_000), down to a 1-second floor. That keeps every window's page count bounded
(threshold / pageSize) so a single failed window is cheap to retry and pagination
stays shallow — while a mass import (a whole discography added in minutes)
collapses into a few tiny dense windows instead of one unpaginable blob.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

ISO_Z = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_THRESHOLD = 10_000
# do not bisect below this many seconds (addedOn has sub-second resolution, but a
# 1s window is already an absurdly dense mass-import bucket; accept overflow there)
MIN_WINDOW_SECONDS = 1
# hard cap on recursion depth as a runaway guard (2y range bisected to 1s ~ 26)
MAX_DEPTH = 40


@dataclass
class Window:
    window_id: str
    min_added_on: str  # inclusive, ISO8601 Z
    max_added_on: str  # exclusive, ISO8601 Z
    expected_count: int | None = None

    def as_dict(self):
        return asdict(self)


def parse_iso(value):
    """Parse an ISO8601 timestamp (with 'Z' or offset) into an aware UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso(dt):
    """Format an aware datetime as ``YYYY-MM-DDTHH:MM:SSZ`` (UTC, second-precision)."""
    return dt.astimezone(timezone.utc).strftime(ISO_Z)


def _label(lo, hi):
    """Human-auditable, unique window id from its bounds (compact ISO range)."""
    return f"{to_iso(lo)}__{to_iso(hi)}".replace(":", "").replace("-", "")


def month_boundaries(start, end):
    """Monthly UTC boundaries covering ``[start, end)`` (start floored to month).

    Returns a list of datetimes ``[b0, b1, ..., bN]`` where consecutive pairs are
    the month windows; the last boundary is ``>= end``.
    """
    cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    bounds = [cur]
    while cur < end:
        year, month = cur.year, cur.month
        if month == 12:
            cur = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            cur = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        bounds.append(cur)
    return bounds


def prescan_monthly(count_fn, start, end):
    """Volumetry pre-scan: rowCount per calendar month over ``[start, end)``.

    ``count_fn(min_iso, max_iso) -> int``. One cheap probe per month
    (~85 for a platform spanning ~7 years). Returns an ordered list of
    ``(min_iso, max_iso, count)``.
    """
    bounds = month_boundaries(start, end)
    out = []
    for lo, hi in zip(bounds, bounds[1:]):
        c = count_fn(to_iso(lo), to_iso(hi))
        out.append((to_iso(lo), to_iso(hi), c))
    return out


def build_plan(count_fn, start, end, threshold=DEFAULT_THRESHOLD):
    """Build a static, gap-free window plan over ``[start, end)``.

    Each returned window has ``expected_count <= threshold`` unless it is already
    at the ``MIN_WINDOW_SECONDS`` floor (an irreducibly dense mass-import bucket,
    kept as-is — the crawl just paginates it deeper). Adjacent windows share a
    boundary, so the union is exactly ``[start, end)`` with no gap or overlap.

    ``count_fn(min_iso, max_iso) -> int`` is the cheap rowCount probe.
    """
    windows: list[Window] = []

    def recurse(lo, hi, depth, known_count=None):
        count = known_count if known_count is not None else count_fn(to_iso(lo), to_iso(hi))
        span = (hi - lo).total_seconds()
        if count <= threshold or span <= MIN_WINDOW_SECONDS or depth >= MAX_DEPTH:
            windows.append(Window(_label(lo, hi), to_iso(lo), to_iso(hi), count))
            return
        mid_epoch = lo.timestamp() + span // 2
        mid = datetime.fromtimestamp(mid_epoch, tz=timezone.utc).replace(microsecond=0)
        # guard against a degenerate split (span too small to halve on second grid)
        if mid <= lo or mid >= hi:
            windows.append(Window(_label(lo, hi), to_iso(lo), to_iso(hi), count))
            return
        recurse(lo, mid, depth + 1)
        recurse(mid, hi, depth + 1)

    # Seed the recursion month by month so the cheap monthly probes are reused as
    # the first level and only over-threshold months pay for deeper bisection.
    bounds = month_boundaries(start, end)
    for lo, hi in zip(bounds, bounds[1:]):
        recurse(lo, hi, 0)
    return windows


def plan_to_dict(windows, threshold, start, end, total_expected=None):
    """Serialisable plan document (metadata + window list)."""
    if total_expected is None:
        total_expected = sum(w.expected_count or 0 for w in windows)
    return {
        "threshold": threshold,
        "start": to_iso(start) if isinstance(start, datetime) else start,
        "end": to_iso(end) if isinstance(end, datetime) else end,
        "window_count": len(windows),
        "total_expected": total_expected,
        "windows": [w.as_dict() for w in windows],
    }


def plan_from_dict(doc):
    """Rebuild the ``Window`` list from a plan document."""
    return [Window(**w) for w in doc["windows"]]


def assert_contiguous(windows):
    """Sanity check: windows are sorted and share boundaries (no gap/overlap).

    Returns a list of human-readable anomaly strings (empty = clean). Used by the
    probe report and the plan builder as an auditable self-check.
    """
    anomalies = []
    ordered = sorted(windows, key=lambda w: w.min_added_on)
    for a, b in zip(ordered, ordered[1:]):
        if a.max_added_on != b.min_added_on:
            anomalies.append(
                f"boundary mismatch: {a.window_id} ends {a.max_added_on} "
                f"but {b.window_id} starts {b.min_added_on}"
            )
    return anomalies


def utc_now():
    """Current UTC time, second-precision (matches the ISO_Z grid)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def final_pass_window(run_start_iso, now=None):
    """The ``[run_start, now)`` window that captures items added during the crawl."""
    now = now or utc_now()
    lo = parse_iso(run_start_iso)
    return Window(f"final__{_label(lo, now)}", run_start_iso, to_iso(now), None)


__all__ = [
    "Window",
    "DEFAULT_THRESHOLD",
    "parse_iso",
    "to_iso",
    "month_boundaries",
    "prescan_monthly",
    "build_plan",
    "plan_to_dict",
    "plan_from_dict",
    "assert_contiguous",
    "utc_now",
    "final_pass_window",
    "timedelta",
]
