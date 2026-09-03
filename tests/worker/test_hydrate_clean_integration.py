"""Integration test: the L2 host orchestrator and the L3 OPS clean-import SNAP
TOGETHER on the bundle contract they share — proven end to end WITHOUT Docker,
network or Essentia.

The clean-hydration pipeline is split across two programs that never run in the
same process in prod:

  * L2 (``worker/trackid_hydrate/hydrate.py``, host / stdlib) fetches a TrackID set
    detail, runs the container driver and ASSEMBLES a per-set "bundle" NDJSON via
    ``assemble_bundle`` (joining the driver output onto the merged tracklist).
  * L3 (``server/api/scripts/import_trackid_clean.py``, VPS) INGESTS that bundle by
    replaying the import/enrichment funnel verbatim against the live DB
    (``import_bundles``).

Their only coupling is the bundle shape. The unit suites cover each side alone
(``worker/trackid_hydrate/test_hydrate.py`` mocks the driver output;
``tests/worker/test_import_trackid_clean.py`` hand-writes bundles). THIS test forges a
TrackID ``detail`` + a driver NDJSON (a ``found`` line and a ``not_found`` line), runs
them through the REAL ``hydrate`` assembler to obtain a bundle, then feeds that exact
bundle to the REAL ``import_bundles`` over an in-memory aiosqlite engine — so a drift
in either program's view of the contract fails here. No Docker / ssh / Essentia /
network: ``hydrate`` is stdlib-only and the driver output is forged, the L3 funnel
runs over SQLite. Parallel-safe (its own StaticPool in-memory engine per run).
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

# ── L3 (server) import — do it BEFORE touching sys.path for the host tool. The worker
# conftest already put server/api on the path; server/api/scripts/import_trackid_clean
# is the only place that submodule lives, so it resolves unambiguously. workers.enrichment
# imports redis + curl_cffi at load, so mock them for the import (same dance as
# test_import_trackid_clean / test_import_beatport_matches). ─────────────────────────
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from scripts.import_trackid_clean import (  # noqa: E402
    _suppress_url_uploads,
    _valid_bundle,
    import_bundles,
)

if _saved_redis is None:
    sys.modules.pop("redis", None)
else:
    sys.modules["redis"] = _saved_redis
del _saved_redis
if _saved_curl is None:
    sys.modules.pop("curl_cffi", None)
else:
    sys.modules["curl_cffi"] = _saved_curl
del _saved_curl

# ── L2 (host orchestrator) import — repo root is already on the path (tests is a
# package), but insert it defensively so `worker.trackid_hydrate.hydrate` resolves. It
# is stdlib-only (no server deps), so this is safe after the L3 import above. ─────────
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../..")
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from models import (  # noqa: E402
    CatalogEntry,
    DJSet,
    SetTrack,
    TrackEmbedding,
    TrackIdIndex,
)
from models.embedding import EMBEDDING_DIM  # noqa: E402
from utils import make_normalized_key  # noqa: E402

from worker.trackid_hydrate.hydrate import (  # noqa: E402
    assemble_bundle,
    build_tracklist,
    parse_driver_output,
)

NOW = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
TRACKID_ID = 777

# A TrackID set detail as L2 fetches it: three non-ID tracks (Song A / B / C) that
# build_tracklist merges into positions 1, 2 and 3.
_DETAIL = {
    "id": TRACKID_ID,
    "slug": "integration-set",
    "title": "Integration Set",
    "url": "https://trackid.net/audiostream/integration-set",
    "duration": "01:00:00",
    "createdOn": "2026-02-01T00:00:00",
    "detectionProcesses": [
        {
            "detectionProcessMusicTracks": [
                {
                    "musicTrackId": 11,
                    "title": "Song A",
                    "artist": "Artist A",
                    "startTime": "00:01:00",
                },
                {
                    "musicTrackId": 12,
                    "title": "Song B",
                    "artist": "Artist B",
                    "startTime": "00:05:00",
                },
                {
                    "musicTrackId": 13,
                    "title": "Song C",
                    "artist": "Artist C",
                    "startTime": "00:09:00",
                },
            ]
        }
    ],
}


def _build_bundle():
    """Run the REAL L2 assembler over a forged detail + driver NDJSON → one bundle.

    Three driver lines, one per position — mirroring the split the real funnel forces:

      * position 1 (Song A): a ``found`` line with a full Deezer hit + estimated BPM +
        embedding, but NO Beatport → the analysis BPM applies (Beatport, authoritative,
        would otherwise win the ``bpm`` column).
      * position 2 (Song B): a ``found`` line with Beatport only → beatport_applied.
      * position 3 (Song C): a ``not_found`` line → no enrichment.

    This exercises hydrate.build_tracklist → parse_driver_output → assemble_bundle
    exactly as the host tool does after the container run.
    """
    tracklist = build_tracklist(_DETAIL)
    driver_ndjson = "\n".join(
        [
            json.dumps(
                {
                    "set_trackid_id": TRACKID_ID,
                    "position": 1,
                    "status": "found",
                    "deezer": {
                        "track": {
                            "id": "900",
                            "duration": 200,
                            "preview": "https://preview",
                            "contributors": [
                                {"id": 7, "name": "Artist A", "role": "Main"}
                            ],
                            "album": {"id": "50", "title": "Alb"},
                        },
                        # URL fields the assembler must DROP when trimming:
                        "preview_url": "https://preview",
                        "cover_catalog_url": None,
                        "cover_album_url": None,
                        # byte fields the assembler must KEEP:
                        "cover_catalog_b64": None,
                        "cover_album_b64": None,
                    },
                    "beatport": None,
                    "bpm": {"value": 128.0, "conf": 2.5},
                    "key": None,
                    "embedding": [0.02] * EMBEDDING_DIM,
                }
            ),
            json.dumps(
                {
                    "set_trackid_id": TRACKID_ID,
                    "position": 2,
                    "status": "found",
                    "deezer": None,
                    "beatport": {"bp_track": {"id": "bp1", "bpm": 130, "key": "9A"}},
                    "bpm": None,
                    "key": "9A",
                    "embedding": None,
                }
            ),
            json.dumps(
                {
                    "set_trackid_id": TRACKID_ID,
                    "position": 3,
                    "status": "not_found",
                    "deezer": None,
                }
            ),
        ]
    )
    driver_index = parse_driver_output(driver_ndjson)
    set_row = {"trackid_id": str(TRACKID_ID), "slug": "integration-set", "score": "88.4"}
    return assemble_bundle(
        set_row, _DETAIL, tracklist, driver_index, set_artwork_b64=None
    )


def _run_import(bundle, *, apply):
    """Ingest ONE assembled bundle through the REAL L3 ``import_bundles`` over an own
    in-memory aiosqlite engine (StaticPool → one shared conn). Seeds the catalog for
    the two tracks + the not_hydrated index row (so the SQLite-incompatible PG
    ON CONFLICT create path is never taken — the dedup path is). Returns (counts,
    snapshot). Mirrors test_import_trackid_clean's async harness."""
    from database import Base
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    async def _go():
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        def _seed(session):
            for title, artist in (
                ("Song A", "Artist A"),
                ("Song B", "Artist B"),
                ("Song C", "Artist C"),
            ):
                session.add(
                    CatalogEntry(
                        title=title,
                        artist=artist,
                        normalized_key=make_normalized_key(title, artist),
                        created_at=NOW,
                    )
                )
            session.add(
                TrackIdIndex(
                    trackid_id=TRACKID_ID,
                    title="Integration Set",
                    hydration_state="not_hydrated",
                )
            )

        async with factory() as db:
            await db.run_sync(_seed)
            await db.commit()

        with _suppress_url_uploads():
            counts = await import_bundles(
                factory, [json.dumps(bundle)], apply=apply, now=NOW
            )

        snapshot = {}

        def _read(session):
            snapshot["sets"] = session.query(DJSet).count()
            snapshot["linked"] = (
                session.query(SetTrack).filter(SetTrack.catalog_id.isnot(None)).count()
            )
            a = (
                session.query(CatalogEntry)
                .filter_by(normalized_key=make_normalized_key("Song A", "Artist A"))
                .one()
            )
            snapshot["a_deezer"] = a.deezer_id
            snapshot["a_bpm"] = a.bpm
            snapshot["a_bpm_source"] = a.bpm_source
            snapshot["a_embeddings"] = (
                session.query(TrackEmbedding).filter_by(catalog_id=a.id).count()
            )
            b = (
                session.query(CatalogEntry)
                .filter_by(normalized_key=make_normalized_key("Song B", "Artist B"))
                .one()
            )
            snapshot["b_beatport"] = b.beatport_id
            idx = session.query(TrackIdIndex).filter_by(trackid_id=TRACKID_ID).one()
            snapshot["hydration"] = idx.hydration_state

        async with factory() as db:
            await db.run_sync(_read)

        await engine.dispose()
        return counts, snapshot

    return asyncio.run(_go())


class TestL2ToL3Contract:
    def test_assembled_bundle_is_valid_and_shaped(self):
        """The L2 output satisfies L3's ``_valid_bundle`` gate and the trimmed shape."""
        bundle = _build_bundle()

        # L3's own admission gate accepts the L2 output.
        assert _valid_bundle(bundle) is True

        assert bundle["trackid_id"] == TRACKID_ID  # coerced to int
        assert bundle["score"] == 88.4  # coerced to float
        assert bundle["detail"] is _DETAIL
        assert len(bundle["tracks"]) == 3

        # position 1: the deezer found line, deezer TRIMMED to the 3 fields L3 reads.
        t1 = bundle["tracks"][0]
        assert set(t1["deezer"]) == {"track", "cover_catalog_b64", "cover_album_b64"}
        assert t1["deezer"]["track"]["id"] == "900"
        assert t1["beatport"] is None
        assert t1["bpm"] == {"value": 128.0, "conf": 2.5}
        assert len(t1["embedding"]) == EMBEDDING_DIM
        assert t1["musicTrackId"] == 11

        # position 2: the beatport found line → beatport kept, deezer null.
        t2 = bundle["tracks"][1]
        assert t2["deezer"] is None
        assert t2["beatport"] == {"bp_track": {"id": "bp1", "bpm": 130, "key": "9A"}}
        assert t2["musicTrackId"] == 12

        # position 3: the not_found line → every enrichment field null.
        t3 = bundle["tracks"][2]
        assert (t3["deezer"], t3["beatport"], t3["bpm"], t3["embedding"]) == (
            None,
            None,
            None,
            None,
        )

    def test_dry_run_ingests_and_counts(self):
        """L3 ingests the L2 bundle in dry-run: counters are accurate, DB rolled back."""
        bundle = _build_bundle()
        counts, snap = _run_import(bundle, apply=False)

        # The contract flowed through: the set imported, both tracks linked, the found
        # line's Deezer/Beatport/BPM/embedding applied, the set hydrated.
        assert counts["total"] == 1
        assert counts["malformed"] == 0
        assert counts["errors"] == 0
        assert counts["sets_imported"] == 1
        assert counts["tracks_linked"] == 3
        assert counts["deezer_applied"] == 1
        assert counts["beatport_applied"] == 1
        assert counts["bpm_set"] == 1
        assert counts["embeddings_inserted"] == 1
        assert counts["hydrated"] == 1

        # Dry-run wrote nothing: the per-set transaction rolled back.
        assert snap["sets"] == 0
        assert snap["linked"] == 0
        assert snap["a_deezer"] is None
        assert snap["hydration"] == "not_hydrated"

    def test_apply_persists_the_assembled_bundle(self):
        """The same L2 bundle, applied, actually lands in the DB through the funnel."""
        bundle = _build_bundle()
        counts, snap = _run_import(bundle, apply=True)

        assert counts["sets_imported"] == 1
        assert counts["deezer_applied"] == 1
        assert counts["hydrated"] == 1

        assert snap["sets"] == 1
        assert snap["linked"] == 3
        assert snap["a_deezer"] == "900"
        assert snap["a_bpm"] == 128.0
        assert snap["a_bpm_source"] == "analysis"
        assert snap["a_embeddings"] == 1
        assert snap["b_beatport"] == "bp1"
        assert snap["hydration"] == "hydrated"
