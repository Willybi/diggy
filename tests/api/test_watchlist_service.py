"""
Tests for the watchlist service (services/watchlist_service.py):
_fetch_deezer_playlist's {} fallback, request_crawl's 12h cooldown and the
get_detail contract (tracks + artists/in_lib, top_artists, top_genres, C3 isolation).
"""
from datetime import datetime, timedelta, timezone

import pytest
from models import (
    Artist,
    CatalogArtist,
    CatalogEntry,
    RadarTrack,
    User,
    UserTrack,
    WatchedEntity,
)
from services import genre_service, watchlist_service

# ── _fetch_deezer_playlist ────────────────────────────────────────────────────

class TestFetchDeezerPlaylist:
    async def test_returns_empty_dict_when_httpx_raises(self, mocker):
        mocker.patch(
            "services.watchlist_service.httpx.AsyncClient",
            side_effect=RuntimeError("network down"),
        )
        result = await watchlist_service._fetch_deezer_playlist("123")
        assert result == {}


# ── request_crawl : cooldown 12h ──────────────────────────────────────────────

async def _make_entity(db, external_id, last_crawled_delta):
    entity = WatchedEntity(
        external_id=external_id,
        source="deezer",
        title="Cooldown PL",
        last_crawled_at=datetime.now(timezone.utc) - last_crawled_delta,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


class TestRequestCrawlCooldown:
    async def test_crawl_just_under_12h_raises(self, db, mocker):
        mocker.patch("services.watchlist_service._trigger_crawl")
        entity = await _make_entity(db, "cd-under", timedelta(hours=11, minutes=59))

        with pytest.raises(ValueError, match="Crawl cooldown: retry in"):
            await watchlist_service.request_crawl(db, entity.id)

    async def test_crawl_just_over_12h_queues(self, db, mocker):
        trigger = mocker.patch("services.watchlist_service._trigger_crawl")
        entity = await _make_entity(db, "cd-over", timedelta(hours=12, minutes=1))

        result = await watchlist_service.request_crawl(db, entity.id)
        assert result == {"status": "crawl_queued", "playlist_id": entity.id}
        trigger.assert_awaited_once()


# ── get_detail : contrat refonte (tracks + agrégats) ──────────────────────────

async def _make_playlist(db, external_id):
    entity = WatchedEntity(external_id=external_id, source="deezer", title="PL")
    db.add(entity)
    await db.flush()
    return entity


async def _make_catalog(
    db, title, artist, *, scope="shared", owner_id=None, genres=None,
    has_artwork=False, has_preview=False,
):
    entry = CatalogEntry(
        title=title,
        artist=artist,
        normalized_key=f"{artist or ''}|{title}".lower(),
        scope=scope,
        owner_id=owner_id,
        genres=genres or [],
        has_artwork=has_artwork,
        has_preview=has_preview,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    return entry


async def _detect(db, entity_id, catalog_id, detected_at=None):
    rt = RadarTrack(
        watched_entity_id=entity_id,
        external_track_id=f"ext-{catalog_id}",
        source="deezer",
        title="t",
        catalog_id=catalog_id,
        detected_at=detected_at or datetime.now(timezone.utc),
    )
    db.add(rt)
    await db.flush()
    return rt


async def _make_artist(db, name, *, has_artwork=False):
    a = Artist(
        name=name,
        normalized_name=name.lower(),
        has_artwork=has_artwork,
        created_at=datetime.now(timezone.utc),
    )
    db.add(a)
    await db.flush()
    return a


async def _link(db, catalog_id, artist_id, *, role="primary", position=0):
    db.add(
        CatalogArtist(
            catalog_id=catalog_id, artist_id=artist_id, role=role, position=position
        )
    )
    await db.flush()


async def _add_to_lib(db, user_id, catalog_id):
    db.add(UserTrack(user_id=user_id, catalog_id=catalog_id))
    await db.flush()


async def _make_user(db, suffix):
    u = User(
        email=f"{suffix}@test.com",
        username=suffix,
        google_id=f"google-{suffix}",
        is_active=True,
        is_admin=False,
    )
    db.add(u)
    await db.flush()
    return u


class TestGetDetailContract:
    async def test_artists_populated_and_ordered_by_position(self, db, auth_user):
        pl = await _make_playlist(db, "pl-artists")
        track = await _make_catalog(db, "Song", "Various")
        await _detect(db, pl.id, track.id)
        a0 = await _make_artist(db, "P0", has_artwork=True)
        a1 = await _make_artist(db, "P1")
        # linked out of order to prove ORDER BY position, not insertion order
        await _link(db, track.id, a1.id, role="featured", position=1)
        await _link(db, track.id, a0.id, role="primary", position=0)
        await db.commit()

        detail = await watchlist_service.get_detail(db, auth_user.id, pl.id)

        assert len(detail.tracks) == 1
        arts = detail.tracks[0].artists
        assert [a.name for a in arts] == ["P0", "P1"]
        assert [a.role for a in arts] == ["primary", "featured"]
        assert arts[0].has_artwork is True
        assert arts[1].has_artwork is False

    async def test_in_lib_true_for_owned_false_otherwise(self, db, auth_user):
        pl = await _make_playlist(db, "pl-lib")
        a = await _make_catalog(db, "A", "x")
        b = await _make_catalog(db, "B", "y")
        await _detect(db, pl.id, a.id)
        await _detect(db, pl.id, b.id)
        await _add_to_lib(db, auth_user.id, a.id)
        await db.commit()

        detail = await watchlist_service.get_detail(db, auth_user.id, pl.id)
        by_id = {t.catalog_id: t for t in detail.tracks}
        assert by_id[a.id].in_lib is True
        assert by_id[b.id].in_lib is False

    async def test_in_lib_all_false_for_guest(self, db, auth_user):
        pl = await _make_playlist(db, "pl-guest")
        a = await _make_catalog(db, "A", "x")
        await _detect(db, pl.id, a.id)
        # even a library membership for some user must never leak to a guest view
        await _add_to_lib(db, auth_user.id, a.id)
        await db.commit()

        detail = await watchlist_service.get_detail(db, None, pl.id)
        assert len(detail.tracks) == 1
        assert detail.tracks[0].in_lib is False

    async def test_top_artists_count_order_and_cap(self, db, auth_user):
        pl = await _make_playlist(db, "pl-top-artists")
        tracks = []
        for i in range(7):
            c = await _make_catalog(db, f"T{i}", f"str{i}")
            await _detect(db, pl.id, c.id)
            tracks.append(c)
        artists = [await _make_artist(db, f"A{i}") for i in range(7)]
        # artist Ai appears on the first (7 - i) tracks -> counts 7,6,5,4,3,2,1
        for i, art in enumerate(artists):
            for t_idx in range(7 - i):
                await _link(db, tracks[t_idx].id, art.id, position=i)
        await db.commit()

        detail = await watchlist_service.get_detail(db, auth_user.id, pl.id)

        assert [a.name for a in detail.top_artists] == [
            "A0", "A1", "A2", "A3", "A4", "A5"
        ]
        assert [a.count for a in detail.top_artists] == [7, 6, 5, 4, 3, 2]
        assert len(detail.top_artists) == 6  # cap 6, "A6" (count 1) dropped

    async def test_top_genres_pct_cap_pillar_and_unknown(self, db, auth_user):
        pl = await _make_playlist(db, "pl-top-genres")
        # counts: weirdcore 6, techno 5, deep house 4, trance 3, dnb 2, hardcore 1
        spec = [
            ("weirdcore", 6),
            ("techno", 5),
            ("deep house", 4),
            ("trance", 3),
            ("dnb", 2),
            ("hardcore", 1),
        ]
        n = 0
        for genre, cnt in spec:
            for _ in range(cnt):
                c = await _make_catalog(db, f"g{n}", f"a{n}", genres=[genre])
                await _detect(db, pl.id, c.id)
                n += 1
        # two genre-less tracks: they must NOT count toward the pct denominator
        for _ in range(2):
            c = await _make_catalog(db, f"g{n}", f"a{n}", genres=[])
            await _detect(db, pl.id, c.id)
            n += 1
        await db.commit()

        saved = dict(genre_service._PILLAR_CACHE)
        genre_service._PILLAR_CACHE.update({
            "techno": ("techno", 0),
            "deep house": ("house", 2),
            "trance": ("trance", 0),
            "dnb": ("dnb", 1),
            "hardcore": ("hardcore", 0),
            # "weirdcore" left unmapped on purpose -> genre_pillar => ('autres', 0)
        })
        try:
            detail = await watchlist_service.get_detail(db, auth_user.id, pl.id)
        finally:
            genre_service._PILLAR_CACHE.clear()
            genre_service._PILLAR_CACHE.update(saved)

        names = [g.name for g in detail.top_genres]
        assert names == ["weirdcore", "techno", "deep house", "trance", "dnb"]
        assert len(detail.top_genres) == 5  # cap 5, "hardcore" (count 1) dropped

        by_name = {g.name: g for g in detail.top_genres}
        # denominator = 21 genre-bearing tracks (the 2 genre-less ones excluded)
        assert by_name["weirdcore"].pct == 29  # round(100 * 6 / 21)
        assert by_name["techno"].pct == 24  # round(100 * 5 / 21)
        # pillar/depth resolved from the cache; unknown genre falls back
        assert (by_name["weirdcore"].pillar, by_name["weirdcore"].depth) == ("autres", 0)
        assert (by_name["techno"].pillar, by_name["techno"].depth) == ("techno", 0)
        assert (by_name["deep house"].pillar, by_name["deep house"].depth) == ("house", 2)

    async def test_foreign_private_track_absent_from_tracks_and_aggregates(
        self, db, auth_user
    ):
        other = await _make_user(db, "otheruser")
        pl = await _make_playlist(db, "pl-isolation")
        shared = await _make_catalog(db, "Shared", "Alpha", genres=["techno"])
        private = await _make_catalog(
            db, "Secret", "Beta", scope="private", owner_id=other.id,
            genres=["techno", "house"],
        )
        await _detect(db, pl.id, shared.id)
        await _detect(db, pl.id, private.id)
        alpha = await _make_artist(db, "Alpha")
        beta = await _make_artist(db, "Beta")
        await _link(db, shared.id, alpha.id)
        await _link(db, private.id, beta.id)
        await db.commit()

        detail = await watchlist_service.get_detail(db, auth_user.id, pl.id)

        # the foreign private track is invisible in the track list…
        assert [t.catalog_id for t in detail.tracks] == [shared.id]
        # …and in every aggregate (no "Beta", no leaked "house" genre)
        assert [a.name for a in detail.top_artists] == ["Alpha"]
        assert {g.name for g in detail.top_genres} == {"techno"}

    async def test_empty_playlist_returns_empty_lists(self, db, auth_user):
        pl = await _make_playlist(db, "pl-empty")
        await db.commit()
        detail = await watchlist_service.get_detail(db, auth_user.id, pl.id)
        assert detail.tracks == []
        assert detail.top_artists == []
        assert detail.top_genres == []
