"""Tests for the artist merge primitive (workers/artist_merge).

Exercises ``merge_artist_into`` against a real sync SQLite session
(``sync_session`` fixture, which ``create_all``s every table incl. the FK
children and the UNIQUE constraints on ``artists.normalized_name`` /
``artist_aliases.normalized_alias``). SQLite does not enforce FKs, so the
primitive must repoint every referencing row EXPLICITLY; it DOES enforce the
UNIQUE indexes, so the alias-uniqueness handling is genuinely tested.
"""
import itertools
import os
import sys

from sqlalchemy import select

# Make the workers package importable (same pattern as test_catalog_merge.py).
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "../../server")
if _SERVER_PATH not in sys.path:
    sys.path.insert(0, _SERVER_PATH)

from models import (  # noqa: E402
    Artist,
    ArtistAlias,
    CatalogArtist,
    SetArtist,
)
from workers.artist_merge import merge_artist_into  # noqa: E402

_seq = itertools.count(1)


def _artist(session, name=None, **fields):
    """Insert an Artist with a unique normalized_name (defaults to name.lower())."""
    n = next(_seq)
    name = name if name is not None else f"Artist {n}"
    artist = Artist(
        name=name,
        normalized_name=fields.pop("normalized_name", name.lower()),
        **fields,
    )
    session.add(artist)
    session.commit()
    return artist


def _alias(session, artist_id, alias, normalized_alias=None):
    row = ArtistAlias(
        artist_id=artist_id,
        alias=alias,
        normalized_alias=normalized_alias if normalized_alias is not None else alias.lower(),
    )
    session.add(row)
    session.commit()
    return row


# ── link reassignment ──────────────────────────────────────────────────────


class TestReassignLinks:
    def test_catalog_artists_simple_move(self, sync_session):
        target = _artist(sync_session)
        source = _artist(sync_session)
        sync_session.add(
            CatalogArtist(catalog_id=55, artist_id=source.id, role="main", position=0)
        )
        sync_session.commit()

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        links = sync_session.execute(select(CatalogArtist)).scalars().all()
        assert len(links) == 1
        assert links[0].catalog_id == 55
        assert links[0].artist_id == target.id

    def test_set_artists_simple_move(self, sync_session):
        target = _artist(sync_session)
        source = _artist(sync_session)
        sync_session.add(SetArtist(set_id=9, artist_id=source.id, position=0))
        sync_session.commit()

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        links = sync_session.execute(select(SetArtist)).scalars().all()
        assert len(links) == 1
        assert links[0].set_id == 9
        assert links[0].artist_id == target.id

    def test_catalog_artists_conflict_drops_duplicate(self, sync_session):
        # Both artists already link catalog 55 → the source row would collide on
        # the (catalog_id, artist_id) PK once repointed, so it is dropped.
        target = _artist(sync_session)
        source = _artist(sync_session)
        sync_session.add(CatalogArtist(catalog_id=55, artist_id=target.id, position=0))
        sync_session.add(CatalogArtist(catalog_id=55, artist_id=source.id, position=1))
        # a non-conflicting source link that must still move
        sync_session.add(CatalogArtist(catalog_id=66, artist_id=source.id, position=0))
        sync_session.commit()

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        links = sync_session.execute(select(CatalogArtist)).scalars().all()
        assert all(link.artist_id == target.id for link in links)
        assert {link.catalog_id for link in links} == {55, 66}
        assert len(links) == 2  # the colliding 55 source row was dropped, not duped

    def test_set_artists_conflict_drops_duplicate(self, sync_session):
        target = _artist(sync_session)
        source = _artist(sync_session)
        sync_session.add(SetArtist(set_id=9, artist_id=target.id, position=0))
        sync_session.add(SetArtist(set_id=9, artist_id=source.id, position=1))
        sync_session.add(SetArtist(set_id=10, artist_id=source.id, position=0))
        sync_session.commit()

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        links = sync_session.execute(select(SetArtist)).scalars().all()
        assert all(link.artist_id == target.id for link in links)
        assert {link.set_id for link in links} == {9, 10}
        assert len(links) == 2


# ── alias handling ──────────────────────────────────────────────────────────


class TestAliasHandling:
    def test_source_aliases_moved_to_target(self, sync_session):
        target = _artist(sync_session, name="Nick León")
        source = _artist(sync_session, name="Nick Leon")
        _alias(sync_session, source.id, "DJ Nick", "dj nick")

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        aliases = {
            a.normalized_alias: a.artist_id
            for a in sync_session.execute(select(ArtistAlias)).scalars().all()
        }
        # the source alias moved to the target...
        assert aliases["dj nick"] == target.id
        # ...and the source spelling was kept as an alias too (accent differs from
        # the target name → normalize keeps them distinct → added).
        assert aliases["nick leon"] == target.id

    def test_redundant_alias_dropped_on_collision_with_target_name(self, sync_session):
        # A source alias whose normalized value equals the TARGET's normalized_name
        # is redundant (it would just repeat the canonical name) → dropped, not moved.
        target = _artist(sync_session, name="Nick León", normalized_name="nick león")
        source = _artist(sync_session, name="Nick Leon", normalized_name="nick leon")
        _alias(sync_session, source.id, "Nick León", "nick león")
        _alias(sync_session, source.id, "Keep Me", "keep me")

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        norms = {
            a.normalized_alias
            for a in sync_session.execute(select(ArtistAlias)).scalars().all()
        }
        assert "nick león" not in norms  # dropped (equals target.normalized_name)
        assert "keep me" in norms  # the non-colliding alias survived the move

    def test_source_name_not_added_when_it_matches_target(self, sync_session):
        # normalize() folds nothing here → both names normalise identically → the
        # source name must NOT be added as a redundant alias.
        target = _artist(sync_session, name="Nick", normalized_name="nick")
        source = _artist(sync_session, name="nick", normalized_name="nick-src")

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        aliases = sync_session.execute(select(ArtistAlias)).scalars().all()
        assert aliases == []

    def test_source_name_added_when_it_differs(self, sync_session):
        target = _artist(sync_session, name="Zoë Mc Pherson")
        source = _artist(sync_session, name="Zoe McPherson")

        merge_artist_into(sync_session, source.id, target.id)
        sync_session.commit()

        aliases = sync_session.execute(select(ArtistAlias)).scalars().all()
        assert len(aliases) == 1
        assert aliases[0].artist_id == target.id
        assert aliases[0].normalized_alias == "zoe mcpherson"


# ── lifecycle & edge cases ──────────────────────────────────────────────────


class TestLifecycle:
    def test_source_is_deleted_and_report_returned(self, sync_session):
        target = _artist(sync_session, name="Keep")
        source = _artist(sync_session, name="Drop")
        source_id = source.id

        report = merge_artist_into(sync_session, source_id, target.id)
        sync_session.commit()

        assert sync_session.get(Artist, source_id) is None
        assert sync_session.get(Artist, target.id) is not None
        assert report == {
            "merged_source": source_id,
            "into": target.id,
            "name": "Drop",
        }

    def test_full_merge_moves_links_and_aliases_then_deletes(self, sync_session):
        # End-to-end: links repointed, alias moved, source name aliased, row gone.
        target = _artist(sync_session, name="Amelie Lens")
        source = _artist(sync_session, name="Amélie Lens")
        sync_session.add(CatalogArtist(catalog_id=1, artist_id=source.id, position=0))
        sync_session.add(SetArtist(set_id=1, artist_id=source.id, position=0))
        _alias(sync_session, source.id, "EXHALE", "exhale")
        source_id = source.id

        merge_artist_into(sync_session, source_id, target.id)
        sync_session.commit()

        assert sync_session.get(Artist, source_id) is None
        cat = sync_session.execute(select(CatalogArtist)).scalar_one()
        assert cat.artist_id == target.id
        st = sync_session.execute(select(SetArtist)).scalar_one()
        assert st.artist_id == target.id
        norms = {
            a.normalized_alias
            for a in sync_session.execute(select(ArtistAlias)).scalars().all()
        }
        assert norms == {"exhale", "amélie lens"}  # moved alias + kept source name

    def test_self_merge_raises_valueerror(self, sync_session):
        a = _artist(sync_session)
        try:
            merge_artist_into(sync_session, a.id, a.id)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError on self-merge")
        # the artist is untouched
        assert sync_session.get(Artist, a.id) is not None

    def test_missing_source_raises_lookuperror(self, sync_session):
        target = _artist(sync_session)
        try:
            merge_artist_into(sync_session, 999999, target.id)
        except LookupError:
            pass
        else:
            raise AssertionError("expected LookupError for missing source")

    def test_missing_target_raises_lookuperror(self, sync_session):
        source = _artist(sync_session)
        try:
            merge_artist_into(sync_session, source.id, 999999)
        except LookupError:
            pass
        else:
            raise AssertionError("expected LookupError for missing target")
