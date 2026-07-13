"""Tests for GET /api/recommendations (C4 — JWT-only endpoint)."""

from datetime import datetime, timezone

from models import CatalogEntry, DJSet, SetTrack, UserOpinion


async def _mk_track(db, title, nk):
    c = CatalogEntry(
        title=title,
        artist="Artist",
        normalized_key=nk,
        bpm=128.0,
        key="8A",
        scope="shared",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _put_in_set(db, catalog_ids):
    s = DJSet(source="trackid", title="Set")
    db.add(s)
    await db.commit()
    await db.refresh(s)
    for pos, cid in enumerate(catalog_ids):
        db.add(SetTrack(set_id=s.id, catalog_id=cid, position=pos))
    await db.commit()
    return s


async def _like(db, user_id, catalog_id):
    db.add(
        UserOpinion(
            user_id=user_id,
            entity_type="track",
            entity_key=str(catalog_id),
            opinion="liked",
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


class TestRecommendationsEndpoint:
    async def test_without_auth_401(self, client):
        r = await client.get("/api/recommendations/")
        assert r.status_code == 401

    async def test_empty_when_no_seed(self, auth_client):
        r = await auth_client.get("/api/recommendations/")
        assert r.status_code == 200
        assert r.json() == {"items": []}

    async def test_shape_and_reco_score(self, auth_client, auth_user, db):
        seed = await _mk_track(db, "Seed", "a|seed")
        b = await _mk_track(db, "B", "a|b")
        await _put_in_set(db, [seed.id, b.id])
        await _like(db, auth_user.id, seed.id)

        r = await auth_client.get("/api/recommendations/")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["id"] == b.id
        assert item["title"] == "B"
        assert item["reco_score"] > 0
        # CatalogEntryOut fields must be present on each item.
        for field in ("has_artwork", "has_preview", "in_lib", "artists", "genres"):
            assert field in item

    async def test_limit_bounds(self, auth_client):
        r = await auth_client.get("/api/recommendations/?limit=0")
        assert r.status_code == 422
        r = await auth_client.get("/api/recommendations/?limit=101")
        assert r.status_code == 422
