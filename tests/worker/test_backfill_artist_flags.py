"""Tests for the OPS artist-flag backfill (scripts/backfill_artist_flags).

Exercises the front-parity tokenizer + the run() engine pass against a sync SQLite
session: a splittable, unlinked, attached, not-yet-flagged artist gets a pending
ArtistFlag with the suggested split; everything else is left alone; dry-run writes
nothing; re-runs are idempotent.
"""
import os
import sys

import pytest
from sqlalchemy import func, select

_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

import scripts.backfill_artist_flags as mod  # noqa: E402
from models import Artist, ArtistFlag, CatalogArtist, CatalogEntry  # noqa: E402
from scripts.backfill_artist_flags import run, split_tokens  # noqa: E402
from utils import normalize  # noqa: E402


class TestSplitTokens:
    def test_slash_splits(self):
        assert split_tokens("Nigel D. Broad/Kieron Bellamy") == [
            "Nigel D. Broad", "Kieron Bellamy"
        ]

    def test_presents_splits_case_insensitive(self):
        assert split_tokens("Oliver Lieb Presents L.S.G.") == ["Oliver Lieb", "L.S.G."]

    def test_ampersand_splits(self):
        assert split_tokens("Adam Beyer & Ida Engberg") == ["Adam Beyer", "Ida Engberg"]

    def test_no_separator_returns_empty(self):
        assert split_tokens("Raoul Konan") == []
        assert split_tokens("Sunn O)))") == []

    def test_separator_present_but_single_token_returns_empty(self):
        # A separator with nothing on one side yields < 2 real tokens → not a split.
        assert split_tokens("Adam Beyer & ") == []


def _artist(session, name, **kw):
    a = Artist(name=name, normalized_name=normalize(name), **kw)
    session.add(a)
    session.commit()
    return a


def _attach(session, artist):
    entry = CatalogEntry(title=f"T{artist.id}", artist=artist.name, normalized_key=f"nk-{artist.id}")
    session.add(entry)
    session.commit()
    session.add(CatalogArtist(catalog_id=entry.id, artist_id=artist.id, role="primary", position=0))
    session.commit()


@pytest.fixture
def seeded(sync_engine, sync_session):
    s = sync_session
    split_a = _artist(s, "Nigel D. Broad/Kieron Bellamy")
    _attach(s, split_a)
    already = _artist(s, "Adam Beyer & Ida Engberg")
    _attach(s, already)
    s.add(ArtistFlag(raw_artist_string=already.name, reason="manual", tokens=["x"], deezer_ids={}, status="pending"))
    s.commit()
    plain = _artist(s, "Raoul Konan")  # not splittable
    _attach(s, plain)
    orphan_split = _artist(s, "A / B")  # splittable but NOT attached
    s.commit()

    mod._engine = sync_engine
    yield {"session": s, "split_id": split_a.id, "already": already.name}
    mod._engine = None


def test_dry_run_flags_nothing(seeded):
    stats = run(apply=False)
    assert stats["flagged"] == 1  # only the unflagged, attached, splittable one
    # No new flag row written (dry-run) — the pre-existing one stays at 1.
    n = seeded["session"].execute(select(func.count(ArtistFlag.id))).scalar_one()
    assert n == 1


def test_apply_creates_pending_flag_with_tokens(seeded):
    run(apply=True)
    s = seeded["session"]
    s.expire_all()
    flag = s.execute(
        select(ArtistFlag).where(ArtistFlag.raw_artist_string == "Nigel D. Broad/Kieron Bellamy")
    ).scalar_one()
    assert flag.status == "pending"
    assert flag.tokens == ["Nigel D. Broad", "Kieron Bellamy"]
    assert flag.reason == "auto_split"


def test_already_flagged_is_skipped(seeded):
    run(apply=True)
    s = seeded["session"]
    # The pre-existing flag for "Adam Beyer & Ida Engberg" is untouched (still ONE row).
    rows = s.execute(
        select(ArtistFlag).where(ArtistFlag.raw_artist_string == seeded["already"])
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].tokens == ["x"]  # not overwritten


def test_apply_is_idempotent(seeded):
    run(apply=True)
    stats = run(apply=True)
    assert stats["flagged"] == 0  # nothing left to flag


def test_orphan_and_plain_not_flagged(seeded):
    run(apply=True)
    s = seeded["session"]
    for name in ("Raoul Konan", "A / B"):
        n = s.execute(
            select(func.count(ArtistFlag.id)).where(ArtistFlag.raw_artist_string == name)
        ).scalar_one()
        assert n == 0
