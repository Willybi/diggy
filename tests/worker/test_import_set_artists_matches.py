"""Tests for the C3 OPS import script (scripts/import_set_artists_matches).

Exercises the testable core ``import_links`` (extracted from ``main`` so it runs
without the CLI) against a real sync SQLite session (``sync_session`` fixture).
Asserts the per-link ROUTING (base link verified + created, deezer link get-or-
created), the idempotence guard (an existing set_artists link is already_linked and
never re-added), the missing-set / artist_missing / placeholder / malformed cases,
the dry-run precision SAMPLE, and dry-run (no commit) vs --apply (committed).

The script REUSES ``deezer_enrich._resolve_or_create_artist`` + the ``SetArtist``
model — these tests assert the wiring + accounting, not the get-or-create internals
(that function has its own tests). Same import/mocking pattern as
test_import_beatport_matches.py (redis + curl_cffi are not installed in the test env
and workers/* import them at load).
"""
import itertools
import os
import sys
from unittest.mock import MagicMock

# Make the workers package importable (same pattern as test_import_beatport_matches).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

_saved_redis = sys.modules.get("redis")
sys.modules.setdefault("redis", MagicMock())
_saved_curl = sys.modules.get("curl_cffi")
sys.modules.setdefault("curl_cffi", MagicMock())

from scripts.import_set_artists_matches import (  # noqa: E402
    _MALFORMED,
    _read_ndjson,
    import_links,
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

from models import Artist, DJSet, SetArtist  # noqa: E402

_nk = itertools.count(1)


def _artist(session, name, deezer_id=None):
    n = next(_nk)
    artist = Artist(name=name, normalized_name=f"norm-{n}-{name.lower()}", deezer_id=deezer_id)
    session.add(artist)
    session.commit()
    return artist


def _set(session, title="A Set", channel=None):
    n = next(_nk)
    dj_set = DJSet(source="trackid", title=title, channel=channel, external_id=f"ext-{n}")
    session.add(dj_set)
    session.commit()
    return dj_set


def _links_of(session, set_id):
    return {
        r[0]
        for r in session.execute(
            SetArtist.__table__.select().with_only_columns(SetArtist.artist_id).where(
                SetArtist.set_id == set_id
            )
        ).all()
    }


class TestBaseLane:
    def test_base_link_verified_and_created(self, sync_session):
        artist = _artist(sync_session, "Bicep")
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Bicep - Live",
            "links": [{"source": "base", "name": "Bicep", "artist_id": artist.id}],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["linked"] == 1
        assert _links_of(sync_session, dj_set.id) == {artist.id}
        link = sync_session.get(SetArtist, (dj_set.id, artist.id))
        assert link.role == "dj"
        assert link.position == 0

    def test_base_artist_missing_is_skipped(self, sync_session):
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Ghost",
            "links": [{"source": "base", "name": "Ghost", "artist_id": 999999}],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["artist_missing"] == 1
        assert stats["linked"] == 0
        assert stats["no_links"] == 1  # set resolved to nothing new
        assert _links_of(sync_session, dj_set.id) == set()


class TestDeezerLane:
    def test_deezer_link_get_or_creates_artist(self, sync_session):
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Peggy Gou b2b Someone",
            "links": [{"source": "deezer", "name": "Peggy Gou", "deezer_id": "555"}],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["linked"] == 1
        # The artist was get-or-created live from the Deezer id.
        artist = (
            sync_session.query(Artist).filter(Artist.deezer_id == "555").one()
        )
        assert artist.name == "Peggy Gou"
        assert _links_of(sync_session, dj_set.id) == {artist.id}

    def test_deezer_link_reuses_existing_artist(self, sync_session):
        existing = _artist(sync_session, "Bonobo", deezer_id="777")
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Bonobo set",
            "links": [{"source": "deezer", "name": "Bonobo", "deezer_id": "777"}],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["linked"] == 1
        # No duplicate artist created.
        assert sync_session.query(Artist).filter(Artist.deezer_id == "777").count() == 1
        assert _links_of(sync_session, dj_set.id) == {existing.id}

    def test_deezer_placeholder_name_is_skipped(self, sync_session):
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "VA compilation",
            "links": [
                {"source": "deezer", "name": "Various Artists", "deezer_id": "1"}
            ],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["placeholder_skipped"] == 1
        assert stats["linked"] == 0
        assert _links_of(sync_session, dj_set.id) == set()


class TestIdempotence:
    def test_existing_link_is_already_linked(self, sync_session):
        artist = _artist(sync_session, "Four Tet")
        dj_set = _set(sync_session)
        sync_session.add(
            SetArtist(set_id=dj_set.id, artist_id=artist.id, role="dj", position=0)
        )
        sync_session.commit()
        record = {
            "set_id": dj_set.id,
            "title": "Four Tet",
            "links": [{"source": "base", "name": "Four Tet", "artist_id": artist.id}],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["already_linked"] == 1
        assert stats["linked"] == 0
        assert _links_of(sync_session, dj_set.id) == {artist.id}  # not duplicated

    def test_same_artist_twice_in_one_set_links_once(self, sync_session):
        artist = _artist(sync_session, "Skee Mask")
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Skee Mask",
            "links": [
                {"source": "base", "name": "Skee Mask", "artist_id": artist.id},
                {"source": "base", "name": "Skee Mask", "artist_id": artist.id},
            ],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["linked"] == 1
        assert stats["already_linked"] == 1  # 2nd occurrence in-run
        assert _links_of(sync_session, dj_set.id) == {artist.id}


class TestSetLevel:
    def test_missing_set(self, sync_session):
        record = {
            "set_id": 999999,
            "title": "Nope",
            "links": [{"source": "base", "name": "x", "artist_id": 1}],
        }

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["missing"] == 1
        assert stats["linked"] == 0

    def test_empty_links_counts_no_links(self, sync_session):
        dj_set = _set(sync_session)
        record = {"set_id": dj_set.id, "title": "Unknown DJ", "links": []}

        stats, sample = import_links(sync_session, [record], apply=True)

        assert stats["no_links"] == 1
        assert stats["linked"] == 0


class TestMalformed:
    def test_malformed_records_and_links(self, sync_session):
        dj_set = _set(sync_session)
        records = [
            _MALFORMED,  # bad JSON line
            {"title": "no id"},  # missing set_id
            {"set_id": True, "links": []},  # bool id
            {"set_id": dj_set.id, "links": "notalist"},  # non-list links
            {
                "set_id": dj_set.id,
                "title": "bad links",
                "links": [
                    {"source": "weird", "name": "x"},  # bad source
                    {"source": "base", "name": "y"},  # base w/o artist_id
                    "notadict",  # non-dict link
                ],
            },
        ]

        stats, sample = import_links(sync_session, records, apply=True)

        assert stats["malformed"] == 4  # bad json + missing id + bool id + non-list links
        assert stats["malformed_link"] == 3  # bad source + base-no-id + non-dict
        assert stats["total"] == 5
        assert _links_of(sync_session, dj_set.id) == set()


class TestDryRunVsApply:
    def test_dry_run_computes_but_writes_nothing(self, sync_session):
        artist = _artist(sync_session, "Objekt")
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Objekt",
            "links": [{"source": "base", "name": "Objekt", "artist_id": artist.id}],
        }

        stats, sample = import_links(sync_session, [record], apply=False)

        assert stats["linked"] == 1  # count accurate (the code ran)
        # ...but nothing committed: rolling back discards the in-memory add.
        sync_session.rollback()
        assert _links_of(sync_session, dj_set.id) == set()

    def test_dry_run_deezer_does_not_persist_new_artist(self, sync_session):
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "New Guy",
            "links": [{"source": "deezer", "name": "New Guy", "deezer_id": "424242"}],
        }

        stats, sample = import_links(sync_session, [record], apply=False)
        assert stats["linked"] == 1
        sync_session.rollback()
        # The get-or-created artist was rolled back too.
        assert sync_session.query(Artist).filter(Artist.deezer_id == "424242").count() == 0

    def test_apply_persists_across_sessions(self, sync_engine):
        from sqlalchemy.orm import Session

        with Session(sync_engine) as s:
            artist = _artist(s, "Overmono")
            dj_set = _set(s)
            set_id, artist_id = dj_set.id, artist.id
            record = {
                "set_id": set_id,
                "title": "Overmono",
                "links": [{"source": "base", "name": "Overmono", "artist_id": artist_id}],
            }
            import_links(s, [record], apply=True)

        with Session(sync_engine) as s2:
            assert s2.get(SetArtist, (set_id, artist_id)) is not None


class TestSample:
    def test_sample_maps_title_to_artist_names(self, sync_session):
        a1 = _artist(sync_session, "Helena Hauff")
        dj_set = _set(sync_session)
        record = {
            "set_id": dj_set.id,
            "title": "Helena Hauff @ Boiler Room",
            "links": [{"source": "base", "name": "Helena Hauff", "artist_id": a1.id}],
        }

        stats, sample = import_links(sync_session, [record], apply=False)

        assert sample == [("Helena Hauff @ Boiler Room", ["Helena Hauff"])]

    def test_no_links_set_absent_from_sample(self, sync_session):
        dj_set = _set(sync_session)
        record = {"set_id": dj_set.id, "title": "Mystery", "links": []}

        stats, sample = import_links(sync_session, [record], apply=False)

        assert sample == []


class TestBatchCommit:
    def test_commits_every_batch(self, sync_engine):
        from sqlalchemy.orm import Session

        with Session(sync_engine) as s:
            records = []
            expected = []
            for _ in range(5):
                artist = _artist(s, f"DJ {next(_nk)}")
                dj_set = _set(s)
                expected.append((dj_set.id, artist.id))
                records.append(
                    {
                        "set_id": dj_set.id,
                        "title": "x",
                        "links": [
                            {"source": "base", "name": artist.name, "artist_id": artist.id}
                        ],
                    }
                )
            stats, _ = import_links(s, records, apply=True, commit_every=2)
            assert stats["linked"] == 5

        with Session(sync_engine) as s2:
            for set_id, artist_id in expected:
                assert s2.get(SetArtist, (set_id, artist_id)) is not None


class TestReadNdjson:
    def test_parses_lines_skips_blank_and_flags_bad_json(self):
        import io

        stream = io.StringIO(
            '{"set_id": 1, "links": []}\n'
            "\n"  # blank line skipped
            "   \n"  # whitespace-only skipped
            "not json at all\n"
            '{"set_id": 2, "links": [{"source": "base", "name": "x", "artist_id": 3}]}\n'
        )

        out = list(_read_ndjson(stream))

        assert len(out) == 3
        assert out[0] == {"set_id": 1, "links": []}
        assert out[1] is _MALFORMED
        assert out[2]["set_id"] == 2
