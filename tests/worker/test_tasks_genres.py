"""
Tests for populate_artist_genres core logic.
Replicates the genre inference algorithm without Celery.
"""
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.orm import Session

from models import Artist, ArtistAlias, CatalogEntry, Genre, artist_genres, catalog_genres


def _populate_artist_genres(session):
    """Replicate core logic of populate_artist_genres task."""
    genres_by_id = {g.id: g.name for g in session.execute(select(Genre)).scalars().all()}
    if not genres_by_id:
        return {"updated": 0}

    artists = session.execute(select(Artist)).scalars().all()
    aliases = session.execute(select(ArtistAlias)).scalars().all()

    artist_names: dict[int, set[str]] = {}
    for a in artists:
        artist_names.setdefault(a.id, set()).add(a.name.lower())
    for al in aliases:
        artist_names.setdefault(al.artist_id, set()).add(al.alias.lower())

    cat_result = session.execute(select(CatalogEntry.id, CatalogEntry.artist))
    cat_by_artist: dict[str, list[int]] = {}
    for cid, cart in cat_result.all():
        if cart:
            cat_by_artist.setdefault(cart.lower(), []).append(cid)

    cg_result = session.execute(select(catalog_genres))
    cat_genre_map: dict[int, set[int]] = {}
    for row in cg_result.all():
        cat_genre_map.setdefault(row[0], set()).add(row[1])

    # Clear existing artist_genres
    session.execute(sa_delete(artist_genres))

    updated = 0
    for a in artists:
        names = artist_names.get(a.id, set())
        cat_ids = []
        for n in names:
            cat_ids.extend(cat_by_artist.get(n, []))
        if not cat_ids:
            continue

        genre_counts: dict[int, int] = {}
        for cid in cat_ids:
            for gid in cat_genre_map.get(cid, set()):
                genre_counts[gid] = genre_counts.get(gid, 0) + 1

        total = len(cat_ids)
        threshold = max(1, int(total * 0.2))

        assigned = []
        for gid, count in genre_counts.items():
            if count >= threshold:
                session.execute(artist_genres.insert().values(artist_id=a.id, genre_id=gid))
                assigned.append(gid)

        if assigned:
            updated += 1

    session.commit()
    return {"updated": updated}


class TestPopulateArtistGenres:
    def test_assigns_genre_above_threshold(self, sync_session):
        s = sync_session
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        g = Genre(name="Tech House")
        s.add_all([a, g])
        s.flush()

        # 3 tracks, all Tech House -> 100% -> assigned
        for i in range(3):
            cat = CatalogEntry(title=f"Track {i}", artist="CamelPhat", normalized_key=f"track {i} - camelphat")
            s.add(cat)
            s.flush()
            s.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
        s.commit()

        result = _populate_artist_genres(s)
        assert result["updated"] == 1

        ag = s.execute(select(artist_genres)).all()
        assert len(ag) == 1
        assert ag[0][1] == g.id

    def test_does_not_assign_below_threshold(self, sync_session):
        s = sync_session
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        g1 = Genre(name="Tech House")
        g2 = Genre(name="Minimal")
        s.add_all([a, g1, g2])
        s.flush()

        # 10 tracks, only 1 has Minimal -> 10% < 20% -> not assigned
        for i in range(10):
            cat = CatalogEntry(title=f"Track {i}", artist="CamelPhat", normalized_key=f"track {i} - camelphat")
            s.add(cat)
            s.flush()
            s.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g1.id))
            if i == 0:
                s.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g2.id))
        s.commit()

        result = _populate_artist_genres(s)
        assert result["updated"] == 1

        ag = s.execute(select(artist_genres)).all()
        genre_ids = {row[1] for row in ag}
        assert g1.id in genre_ids
        assert g2.id not in genre_ids

    def test_idempotent(self, sync_session):
        s = sync_session
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        g = Genre(name="Tech House")
        s.add_all([a, g])
        s.flush()

        cat = CatalogEntry(title="Track", artist="CamelPhat", normalized_key="track - camelphat")
        s.add(cat)
        s.flush()
        s.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
        s.commit()

        r1 = _populate_artist_genres(s)
        r2 = _populate_artist_genres(s)
        assert r1["updated"] == 1
        assert r2["updated"] == 1

        # Still only 1 link
        ag = s.execute(select(artist_genres)).all()
        assert len(ag) == 1

    def test_matches_via_alias(self, sync_session):
        s = sync_session
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        g = Genre(name="Tech House")
        s.add_all([a, g])
        s.flush()
        s.add(ArtistAlias(artist_id=a.id, alias="Camel Phat", normalized_alias="camel phat"))

        # Catalog entry uses the alias name
        cat = CatalogEntry(title="Track", artist="Camel Phat", normalized_key="track - camel phat")
        s.add(cat)
        s.flush()
        s.execute(catalog_genres.insert().values(catalog_id=cat.id, genre_id=g.id))
        s.commit()

        result = _populate_artist_genres(s)
        assert result["updated"] == 1

    def test_no_genres_no_update(self, sync_session):
        s = sync_session
        result = _populate_artist_genres(s)
        assert result["updated"] == 0
