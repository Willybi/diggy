"""Parsing utilities for TrackID.net API data."""

from datetime import datetime, timezone


def parse_timespan_to_ms(timespan: str | None) -> int | None:
    """Parse .NET TimeSpan to milliseconds.

    Formats: "HH:MM:SS.fffffff" or "d.HH:MM:SS.fffffff"
    The fractional part has up to 7 digits (100-nanosecond ticks).
    """
    if not timespan or not timespan.strip():
        return None

    s = timespan.strip()
    days = 0

    # Handle optional days prefix: "d.HH:MM:SS..."
    if "." in s.split(":")[0]:
        parts = s.split(".", 1)
        days = int(parts[0])
        s = parts[1]

    # Split time and fractional seconds
    frac_ms = 0
    if "." in s:
        time_part, frac_part = s.rsplit(".", 1)
        # Convert 7-digit fraction (100ns ticks) to ms
        frac_ms = int(frac_part[:7].ljust(7, "0")) // 10_000
    else:
        time_part = s

    h, m, sec = time_part.split(":")
    total_ms = (
        days * 86_400_000
        + int(h) * 3_600_000
        + int(m) * 60_000
        + int(sec) * 1_000
        + frac_ms
    )
    return total_ms


def parse_trackid_date(date_str: str | None) -> datetime | None:
    """Parse ISO 8601 date from TrackID, treating .NET default as None."""
    if not date_str or not date_str.strip():
        return None

    s = date_str.strip()

    # .NET default date = null disguised
    if s.startswith("0001-01-01"):
        return None

    # Remove trailing Z and parse
    s = s.rstrip("Z")
    try:
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_id_track(title: str | None, artist: str | None) -> bool:
    """Detect unidentified tracks ('ID - ID', 'ID', empty, null)."""
    id_markers = {"id", "id - id", "?", "??", "unknown", ""}

    t = (title or "").strip().lower()
    a = (artist or "").strip().lower()

    if t in id_markers and a in id_markers:
        return True
    if t in id_markers and not a:
        return True
    if not t:
        return True

    return False
