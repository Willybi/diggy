"""Local SQLite staging store: raw listing mirror + per-window crawl checkpoint.

The staging table ``trackid_index_staging`` is a RAW MIRROR — no filtering at all
(``isDeleted`` / ``status`` kept verbatim), one row per ``trackid_id`` (the PK),
with a ``raw_json`` column holding the full untouched listing item (zero loss).
Upsert is idempotent on ``trackid_id`` so re-crawling a window (a resume, a
boundary overlap, the final pass) never duplicates nor loses a row.

``crawl_windows`` is the resume checkpoint: one row per plan window with its state
(pending / in_progress / done / failed / overflow) and ``pages_done`` so an
interrupted crawl resumes mid-window without re-fetching completed pages.
``crawl_meta`` is a tiny key/value bag (run_start, total_known, ...).
"""

import sqlite3

from .mapping import COLUMNS, dumps_compact

# Internal bookkeeping columns kept in staging but NOT part of the export
# contract (the export emits only mapping.COLUMNS, in order).
_STAGING_DDL = """
CREATE TABLE IF NOT EXISTS trackid_index_staging (
    trackid_id          INTEGER PRIMARY KEY,
    slug                TEXT,
    title               TEXT,
    channel             TEXT,
    styles              TEXT,
    status              INTEGER,
    is_deleted          INTEGER,
    track_count         INTEGER,
    duration            TEXT,
    time_hit_rate       REAL,
    track_hit_rate      REAL,
    processing_priority INTEGER,
    artwork_url         TEXT,
    added_on            TEXT,
    created_on          TEXT,
    added_by            TEXT,
    added_by_id         INTEGER,
    audio_stream_type   INTEGER,
    external_id         TEXT,
    url                 TEXT,
    favourite_count     INTEGER,
    like_count          INTEGER,
    average_rating      REAL,
    raw_json            TEXT,
    window_id           TEXT,
    first_seen_at       TEXT,
    last_seen_at        TEXT
);
"""

_WINDOWS_DDL = """
CREATE TABLE IF NOT EXISTS crawl_windows (
    window_id      TEXT PRIMARY KEY,
    min_added_on   TEXT NOT NULL,
    max_added_on   TEXT NOT NULL,
    expected_count INTEGER,
    observed_count INTEGER,
    pages_done     INTEGER NOT NULL DEFAULT 0,
    state          TEXT NOT NULL DEFAULT 'pending',
    overflow       INTEGER NOT NULL DEFAULT 0,
    error          TEXT,
    updated_at     TEXT
);
"""

_META_DDL = """
CREATE TABLE IF NOT EXISTS crawl_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# The upsert updates every mirror column from the fresh item but preserves the
# original first_seen_at (only last_seen_at moves forward).
_UPSERT_SQL = """
INSERT INTO trackid_index_staging (
    trackid_id, slug, title, channel, styles, status, is_deleted, track_count,
    duration, time_hit_rate, track_hit_rate, processing_priority, artwork_url,
    added_on, created_on, added_by, added_by_id, audio_stream_type, external_id,
    url, favourite_count, like_count, average_rating, raw_json, window_id,
    first_seen_at, last_seen_at
) VALUES (
    :trackid_id, :slug, :title, :channel, :styles, :status, :is_deleted,
    :track_count, :duration, :time_hit_rate, :track_hit_rate,
    :processing_priority, :artwork_url, :added_on, :created_on, :added_by,
    :added_by_id, :audio_stream_type, :external_id, :url, :favourite_count,
    :like_count, :average_rating, :raw_json, :window_id, :now, :now
)
ON CONFLICT(trackid_id) DO UPDATE SET
    slug=excluded.slug, title=excluded.title, channel=excluded.channel,
    styles=excluded.styles, status=excluded.status, is_deleted=excluded.is_deleted,
    track_count=excluded.track_count, duration=excluded.duration,
    time_hit_rate=excluded.time_hit_rate,
    track_hit_rate=excluded.track_hit_rate,
    processing_priority=excluded.processing_priority,
    artwork_url=excluded.artwork_url, added_on=excluded.added_on,
    created_on=excluded.created_on, added_by=excluded.added_by,
    added_by_id=excluded.added_by_id, audio_stream_type=excluded.audio_stream_type,
    external_id=excluded.external_id, url=excluded.url,
    favourite_count=excluded.favourite_count, like_count=excluded.like_count,
    average_rating=excluded.average_rating, raw_json=excluded.raw_json,
    window_id=excluded.window_id, last_seen_at=excluded.last_seen_at
"""

_ACTIVE_STATES = ("pending", "in_progress", "failed")


class Store:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(_STAGING_DDL)
        self.conn.execute(_WINDOWS_DDL)
        self.conn.execute(_META_DDL)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ---- meta -----------------------------------------------------------
    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO crawl_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def get_meta(self, key, default=None):
        row = self.conn.execute(
            "SELECT value FROM crawl_meta WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    # ---- staging upsert -------------------------------------------------
    def upsert_items(self, rows, now):
        """Idempotent upsert of mapped rows (dicts keyed by the contract columns)."""
        if not rows:
            return
        params = [dict(r, now=now) for r in rows]
        self.conn.executemany(_UPSERT_SQL, params)
        self.conn.commit()

    def staging_count(self):
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM trackid_index_staging"
        ).fetchone()["n"]

    def id_bounds(self):
        row = self.conn.execute(
            "SELECT MIN(trackid_id) AS lo, MAX(trackid_id) AS hi "
            "FROM trackid_index_staging"
        ).fetchone()
        return row["lo"], row["hi"]

    # ---- window checkpoint ----------------------------------------------
    def load_plan(self, windows, now):
        """Insert plan windows as ``pending`` if not already present (idempotent).

        An existing window (a resumed run) keeps its state/pages_done — only new
        windows are added, so re-loading the same plan never rewinds progress.
        """
        for w in windows:
            self.conn.execute(
                "INSERT INTO crawl_windows "
                "(window_id, min_added_on, max_added_on, expected_count, "
                " pages_done, state, overflow, updated_at) "
                "VALUES (?, ?, ?, ?, 0, 'pending', 0, ?) "
                "ON CONFLICT(window_id) DO NOTHING",
                (w.window_id, w.min_added_on, w.max_added_on, w.expected_count, now),
            )
        self.conn.commit()

    def get_window(self, window_id):
        return self.conn.execute(
            "SELECT * FROM crawl_windows WHERE window_id=?", (window_id,)
        ).fetchone()

    def active_windows(self):
        """Windows still needing work (pending/in_progress/failed-to-retry).

        Used for REPORTING (the end-of-run ``failed`` list, state counts). The
        in-run crawl loop uses ``windows_to_crawl`` instead — a window that
        FAILED this run must NOT be re-selected this run (see that method).
        """
        placeholders = ",".join("?" for _ in _ACTIVE_STATES)
        return self.conn.execute(
            f"SELECT * FROM crawl_windows WHERE state IN ({placeholders}) "
            "ORDER BY min_added_on",
            _ACTIVE_STATES,
        ).fetchall()

    def windows_to_crawl(self):
        """Windows to crawl THIS run: ``pending``/``in_progress`` only, excluding
        the final-pass windows (``final__*``, handled separately by run_crawl).

        Deliberately EXCLUDES ``failed`` so a window that hits a persistent HTTP
        error this run is not immediately re-selected (which would busy-loop and
        hammer the API). It is retried on the NEXT run via ``reset_failed_windows``.
        """
        rows = self.conn.execute(
            "SELECT * FROM crawl_windows "
            "WHERE state IN ('pending', 'in_progress') "
            "ORDER BY min_added_on"
        ).fetchall()
        return [w for w in rows if not w["window_id"].startswith("final__")]

    def reset_failed_windows(self, now):
        """Reset ``failed`` windows back to ``pending`` for a between-run retry.

        Only ``state`` changes — ``pages_done`` is PRESERVED so the retry resumes
        where the failed run stopped. Called once at run start; windows that fail
        during the run stay ``failed`` until the next run.
        """
        self.conn.execute(
            "UPDATE crawl_windows SET state='pending', updated_at=? "
            "WHERE state='failed'",
            (now,),
        )
        self.conn.commit()

    def update_window(self, window_id, now, **fields):
        if not fields:
            return
        fields["updated_at"] = now
        assignments = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [window_id]
        self.conn.execute(
            f"UPDATE crawl_windows SET {assignments} WHERE window_id=?", values
        )
        self.conn.commit()

    def window_state_counts(self):
        rows = self.conn.execute(
            "SELECT state, COUNT(*) AS n FROM crawl_windows GROUP BY state"
        ).fetchall()
        return {r["state"]: r["n"] for r in rows}

    def sum_expected(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(expected_count), 0) AS s FROM crawl_windows "
            "WHERE expected_count IS NOT NULL"
        ).fetchone()
        return row["s"]

    # ---- export ---------------------------------------------------------
    def iter_export_rows(self):
        """Yield every staging row as a dict in the EXACT contract column order."""
        cols = ", ".join(COLUMNS)
        cur = self.conn.execute(
            f"SELECT {cols} FROM trackid_index_staging ORDER BY trackid_id"
        )
        for row in cur:
            yield {c: row[c] for c in COLUMNS}

    # ---- volumetry queries ----------------------------------------------
    def top_channels(self, limit=25):
        return [
            (r["channel"], r["n"])
            for r in self.conn.execute(
                "SELECT channel, COUNT(*) AS n FROM trackid_index_staging "
                "GROUP BY channel ORDER BY n DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ]

    def count_by_year(self, field="added_on"):
        if field not in ("added_on", "created_on"):
            raise ValueError(f"unsupported field {field!r}")
        return [
            (r["y"], r["n"])
            for r in self.conn.execute(
                f"SELECT substr({field}, 1, 4) AS y, COUNT(*) AS n "
                "FROM trackid_index_staging GROUP BY y ORDER BY y"
            ).fetchall()
        ]

    def hitrate_histogram(self, field="track_hit_rate", buckets=10):
        """Counts of ``field`` in ``buckets`` equal bins over [0, 1]."""
        if field not in ("track_hit_rate", "time_hit_rate"):
            raise ValueError(f"unsupported field {field!r}")
        hist = [0] * buckets
        for r in self.conn.execute(
            f"SELECT {field} AS v FROM trackid_index_staging WHERE {field} IS NOT NULL"
        ):
            v = r["v"] or 0.0
            idx = min(buckets - 1, max(0, int(v * buckets)))
            hist[idx] += 1
        return hist

    def deleted_count(self):
        return self.conn.execute(
            "SELECT COUNT(*) AS n FROM trackid_index_staging WHERE is_deleted=1"
        ).fetchone()["n"]

    def status_distribution(self):
        return {
            r["status"]: r["n"]
            for r in self.conn.execute(
                "SELECT status, COUNT(*) AS n FROM trackid_index_staging "
                "GROUP BY status ORDER BY n DESC"
            ).fetchall()
        }

    def mass_import_spikes(self, min_count=200, limit=50):
        """(added_by, minute, count) buckets where one user imported a burst.

        Groups by uploader + the minute of ``added_on`` — a discography dumped in
        minutes shows up as a single high-count bucket.
        """
        return [
            (r["added_by"], r["minute"], r["n"])
            for r in self.conn.execute(
                "SELECT added_by, substr(added_on, 1, 16) AS minute, COUNT(*) AS n "
                "FROM trackid_index_staging "
                "WHERE added_on IS NOT NULL "
                "GROUP BY added_by, minute HAVING n >= ? "
                "ORDER BY n DESC LIMIT ?",
                (min_count, limit),
            ).fetchall()
        ]

    def styles_presence(self):
        """(with_styles, without_styles) counts — a non-empty ``styles`` array."""
        with_styles = self.conn.execute(
            "SELECT COUNT(*) AS n FROM trackid_index_staging "
            "WHERE styles IS NOT NULL AND styles NOT IN ('[]', '')"
        ).fetchone()["n"]
        total = self.staging_count()
        return with_styles, total - with_styles


def row_to_export_values(row):
    """Serialise a contract-keyed row dict to a flat list of strings for CSV.

    ``styles`` and ``raw_json`` are already compact JSON strings in staging; any
    other value is stringified, ``None`` -> empty string. (``styles``/``raw_json``
    pass through unchanged so the CSV carries them as JSON, per the contract.)
    """
    out = []
    for col in COLUMNS:
        val = row.get(col)
        if val is None:
            out.append("")
        elif isinstance(val, (list, dict)):  # defensive: re-serialise if needed
            out.append(dumps_compact(val))
        else:
            out.append(str(val))
    return out
