"""Tests for services/artist_service.py."""
import pytest
from services import artist_service


class TestListArtists:
    async def test_returns_dict_with_expected_keys(self, db, auth_user):
        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=False, ids=None, limit=20, offset=0
        )
        assert isinstance(result, dict)
        assert "items" in result
        assert "total" in result
        assert "pillarCounts" in result

    async def test_returns_empty_when_no_artists(self, db, auth_user):
        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=False, ids=None, limit=20, offset=0
        )
        assert result["total"] == 0
        assert result["items"] == []

    async def test_filters_by_query(self, db, auth_user):
        from models import Artist
        a = Artist(name="Aphex Twin", normalized_name="aphex twin", deezer_id="99")
        db.add(a)
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q="aphex",
            no_deezer=False, ids=None, limit=20, offset=0
        )
        assert result["total"] == 1
        assert result["items"][0]["name"] == "Aphex Twin"

    async def test_no_deezer_filter(self, db, auth_user):
        from models import Artist, CatalogArtist, CatalogEntry
        a1 = Artist(name="WithDeezer", normalized_name="withdeezer", deezer_id="1")
        a2 = Artist(name="NoDeezer", normalized_name="nodeezer")
        orphan = Artist(name="OrphanNoDeezer", normalized_name="orphannodeezer")
        cat = CatalogEntry(title="T", artist="NoDeezer", normalized_key="t - nodeezer")
        db.add_all([a1, a2, orphan, cat])
        await db.flush()
        db.add(CatalogArtist(catalog_id=cat.id, artist_id=a2.id, role="primary", position=0))
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=True, ids=None, limit=20, offset=0
        )
        names = [a["name"] for a in result["items"]]
        assert "NoDeezer" in names
        assert "WithDeezer" not in names
        # A fully orphaned unlinked row (no catalog, no set) stays hidden.
        assert "OrphanNoDeezer" not in names

    async def test_no_deezer_hides_dormant_unsplittable(self, db, auth_user):
        from models import Artist, CatalogArtist, CatalogEntry

        # abandoned (>= 3 attempts) + no separator → dormant, hidden.
        dormant = Artist(name="Raoul Konan", normalized_name="raoul konan", deezer_search_attempts=3)
        # abandoned but splittable → stays visible (actionable via split).
        splittable = Artist(name="Adam & Eve", normalized_name="adam & eve", deezer_search_attempts=3)
        # still being searched → visible.
        active = Artist(name="Fresh Name", normalized_name="fresh name", deezer_search_attempts=0)
        db.add_all([dormant, splittable, active])
        await db.flush()
        for a in (dormant, splittable, active):
            cat = CatalogEntry(title=f"T{a.id}", artist=a.name, normalized_key=f"nk-{a.id}")
            db.add(cat)
            await db.flush()
            db.add(
                CatalogArtist(catalog_id=cat.id, artist_id=a.id, role="primary", position=0)
            )
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=True, ids=None, limit=20, offset=0,
        )
        names = [a["name"] for a in result["items"]]
        assert "Adam & Eve" in names  # splittable → kept
        assert "Fresh Name" in names  # still searching → kept
        assert "Raoul Konan" not in names  # dormant dead-end → hidden
        assert result["dormant_count"] == 1

    async def test_pagination_stable_on_tied_catalog_count(self, db, auth_user):
        """Regression: ex-aequo rows (same nb_catalog) must not repeat or skip
        across two consecutive LIMIT/OFFSET pages. Artist.id is the total-order
        tiebreaker, so infinite scroll never returns the same artist twice.

        Each page runs in its OWN session — faithful to the real per-request DB
        sessions the infinite scroll uses, and it sidesteps the SQLite-only
        artwork rollback (the artwork query is PostgreSQL syntax) that would
        otherwise poison a single reused session between the two calls.
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from models import Artist

        # Four artists, none linked to any catalog track → all nb_catalog=0 (tied).
        db.add_all([
            Artist(name=f"Tie {i}", normalized_name=f"tie {i}") for i in range(4)
        ])
        await db.commit()

        maker = async_sessionmaker(db.bind, expire_on_commit=False)

        async def page(offset):
            async with maker() as session:
                res = await artist_service.list_artists(
                    session, auth_user.id, sort="catalog", family=None, q=None,
                    no_deezer=False, ids=None, limit=2, offset=offset,
                )
            return [i["id"] for i in res["items"]]

        page1 = await page(0)
        page2 = await page(2)

        # No id on both pages; the union covers all four distinctly.
        assert len(page1) == 2 and len(page2) == 2
        assert set(page1).isdisjoint(page2)
        combined = page1 + page2
        assert len(set(combined)) == 4
        # Ex-aequo → deterministic ascending Artist.id order across the pages.
        assert combined == sorted(combined)

    async def test_followed_filter_returns_only_followed(self, db, auth_user):
        from datetime import datetime, timezone

        from models import Artist, FollowedArtist

        followed = Artist(name="Followed One", normalized_name="followed one")
        other = Artist(name="Other One", normalized_name="other one")
        db.add_all([followed, other])
        await db.commit()
        await db.refresh(followed)
        db.add(
            FollowedArtist(
                user_id=auth_user.id,
                artist_id=followed.id,
                followed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=False, ids=None, limit=20, offset=0, followed=True
        )
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "Followed One"
        assert result["items"][0]["following"] is True

    async def test_following_flag_reflects_state_without_filter(self, db, auth_user):
        from datetime import datetime, timezone

        from models import Artist, FollowedArtist

        followed = Artist(name="Fol", normalized_name="fol")
        plain = Artist(name="Plain", normalized_name="plain")
        db.add_all([followed, plain])
        await db.commit()
        await db.refresh(followed)
        db.add(
            FollowedArtist(
                user_id=auth_user.id,
                artist_id=followed.id,
                followed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

        result = await artist_service.list_artists(
            db, auth_user.id, sort="name", family=None, q=None,
            no_deezer=False, ids=None, limit=20, offset=0, followed=False
        )
        by_name = {i["name"]: i for i in result["items"]}
        assert by_name["Fol"]["following"] is True
        assert by_name["Plain"]["following"] is False


class TestGetDetail:
    async def test_raises_lookup_error_for_missing_artist(self, db):
        with pytest.raises(LookupError, match="not found"):
            await artist_service.get_detail(db, 9999999)

    async def test_returns_dict_for_valid_artist(self, db):
        from models import Artist
        a = Artist(name="Test Artist", normalized_name="test artist")
        db.add(a)
        await db.commit()
        await db.refresh(a)

        result = await artist_service.get_detail(db, a.id)
        assert result.name == "Test Artist"

    async def test_set_lists_all_artists_ordered_by_position(self, db):
        from models import Artist, DJSet, SetArtist

        page = Artist(name="Page Artist", normalized_name="page artist")
        guest = Artist(name="B2B Guest", normalized_name="b2b guest")
        s = DJSet(title="B2B Set", source="trackid")
        db.add_all([page, guest, s])
        await db.commit()
        await db.refresh(page)
        await db.refresh(guest)
        await db.refresh(s)
        # Insert out of position order to prove the fetch orders by position.
        db.add_all([
            SetArtist(set_id=s.id, artist_id=guest.id, role="guest", position=1),
            SetArtist(set_id=s.id, artist_id=page.id, role="headliner", position=0),
        ])
        await db.commit()

        result = await artist_service.get_detail(db, page.id)
        assert len(result.sets) == 1
        # All artists of the set, not just the page one, ordered by position.
        assert result.sets[0].artists == ["Page Artist", "B2B Guest"]

    async def test_set_duration_ms_populated_and_none(self, db):
        from models import Artist, DJSet, SetArtist

        a = Artist(name="Durationy", normalized_name="durationy")
        with_dur = DJSet(title="Timed Set", source="trackid", duration_ms=5400000)
        without_dur = DJSet(title="Untimed Set", source="trackid")
        db.add_all([a, with_dur, without_dur])
        await db.commit()
        await db.refresh(a)
        await db.refresh(with_dur)
        await db.refresh(without_dur)
        db.add_all([
            SetArtist(set_id=with_dur.id, artist_id=a.id, role="headliner"),
            SetArtist(set_id=without_dur.id, artist_id=a.id, role="headliner"),
        ])
        await db.commit()

        result = await artist_service.get_detail(db, a.id)
        by_title = {s.title: s for s in result.sets}
        assert by_title["Timed Set"].duration_ms == 5400000
        assert by_title["Untimed Set"].duration_ms is None

    async def test_set_with_only_current_artist_still_lists_it(self, db):
        from models import Artist, DJSet, SetArtist

        a = Artist(name="Solo Act", normalized_name="solo act")
        s = DJSet(title="Solo Set", source="trackid")
        db.add_all([a, s])
        await db.commit()
        await db.refresh(a)
        await db.refresh(s)
        db.add(SetArtist(set_id=s.id, artist_id=a.id, role="headliner"))
        await db.commit()

        result = await artist_service.get_detail(db, a.id)
        assert len(result.sets) == 1
        assert result.sets[0].artists == ["Solo Act"]

    async def test_artist_without_sets_returns_empty_list(self, db):
        from models import Artist

        a = Artist(name="Setless", normalized_name="setless")
        db.add(a)
        await db.commit()
        await db.refresh(a)

        result = await artist_service.get_detail(db, a.id)
        assert result.sets == []

    async def test_lib_data_scoped_to_viewer_no_cross_user_leak(self, db):
        """Regression A1-01/A6-01: the library subquery MUST be scoped to the
        viewer. Otherwise Artist Detail unions every user's user_tracks — leaking
        another user's private Rekordbox bpm/key/mytags (served as
        bpm_source='rekordbox') and their library membership, and duplicating a
        track held by several users.

        Each get_detail runs in its OWN session (faithful to the real per-request
        sessions) — this sidesteps the SQLite pillar-cache rollback expiring ORM
        objects when several calls share a single reused session.
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from models import Artist, CatalogArtist, CatalogEntry, User, UserTrack

        def _mk_user(email, gid):
            return User(
                email=email, username=email.split("@")[0], google_id=gid,
                is_active=True, is_admin=False,
            )

        owner = _mk_user("owner@t.com", "g-owner")
        other = _mk_user("other@t.com", "g-other")
        second_holder = _mk_user("second@t.com", "g-second")
        artist = Artist(name="Shared Act", normalized_name="shared act")
        db.add_all([owner, other, second_holder, artist])
        await db.flush()

        entry = CatalogEntry(
            title="Common Track", artist="Shared Act",
            normalized_key="shared act|common track", scope="shared",
            bpm=120.0, key="8A", bpm_source="beatport",
        )
        db.add(entry)
        await db.flush()
        db.add(CatalogArtist(
            catalog_id=entry.id, artist_id=artist.id, role="primary", position=0
        ))
        # owner AND second_holder both hold the same catalog row, with distinct
        # private Rekordbox values.
        db.add(UserTrack(
            user_id=owner.id, catalog_id=entry.id, source="rekordbox_import",
            rb_bpm=130.0, rb_key="9A", rb_mytags=["Peak Time"],
        ))
        db.add(UserTrack(
            user_id=second_holder.id, catalog_id=entry.id, source="rekordbox_import",
            rb_bpm=88.0, rb_key="1A", rb_mytags=["Warmup"],
        ))
        await db.commit()
        artist_id, owner_id, other_id = artist.id, owner.id, other.id

        maker = async_sessionmaker(db.bind, expire_on_commit=False)

        async def detail_for(viewer_id):
            async with maker() as session:
                return await artist_service.get_detail(session, artist_id, viewer_id)

        # A viewer who does NOT hold the track and a guest see catalog values
        # only — never another user's Rekordbox data — and a single row.
        for viewer_id in (other_id, None):
            detail = await detail_for(viewer_id)
            assert len(detail.catalog_tracks) == 1  # no dup despite 2 holders
            t = detail.catalog_tracks[0]
            assert t.in_lib is False
            assert t.bpm == 120.0 and t.key == "8A"
            assert t.bpm_source == "beatport"  # not the leaked 'rekordbox'
            assert t.style is None
            assert detail.stats["nb_lib"] == 0

        # Positive control: the owner still sees THEIR own library row (the fix
        # scopes, it does not blank), and only theirs (not second_holder's).
        own = await detail_for(owner_id)
        assert len(own.catalog_tracks) == 1
        ot = own.catalog_tracks[0]
        assert ot.in_lib is True
        assert ot.bpm == 130.0 and ot.key == "9A"
        assert ot.bpm_source == "rekordbox"
        assert ot.style == "Peak Time"
        assert own.stats["nb_lib"] == 1


class TestListArtistsLikeEscape:
    """A6-06: a literal % / _ in the artist search must match literally, not as
    a LIKE wildcard. Without like_escape, 'A%B' would also match 'AXB'."""

    @staticmethod
    async def _seed(db):
        from models import Artist

        db.add_all([
            Artist(name="A%B", normalized_name="a%b"),
            Artist(name="AXB", normalized_name="axb"),
            Artist(name="A_B", normalized_name="a_b"),
            Artist(name="AZB", normalized_name="azb"),
        ])
        await db.commit()

    async def test_percent_matches_literally(self, db, auth_user):
        await self._seed(db)
        res = await artist_service.list_artists(
            db, auth_user.id, sort="alpha", family=None, q="A%B",
            no_deezer=False, ids=None, limit=20, offset=0,
        )
        assert {i["name"] for i in res["items"]} == {"A%B"}

    async def test_underscore_matches_literally(self, db, auth_user):
        await self._seed(db)
        res = await artist_service.list_artists(
            db, auth_user.id, sort="alpha", family=None, q="A_B",
            no_deezer=False, ids=None, limit=20, offset=0,
        )
        assert {i["name"] for i in res["items"]} == {"A_B"}


class TestLinkToDeezer:
    @staticmethod
    def _stub_httpx(monkeypatch, name="Canonical"):
        """Avoid the real Deezer call (returns a name, no picture).

        link_to_deezer now fetches over httpx (async) rather than requests, so
        the stub swaps httpx.AsyncClient for an async-context-manager fake.
        """
        from services import artist_service

        class _Resp:
            def json(self):
                return {"name": name}

        class _FakeClient:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, *a, **k):
                return _Resp()

        monkeypatch.setattr(artist_service.httpx, "AsyncClient", _FakeClient)

    async def _catalog_entry(self, db, key):
        from datetime import datetime, timezone

        from models import CatalogEntry

        entry = CatalogEntry(
            title=f"Track {key}",
            artist="X",
            normalized_key=key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.flush()
        return entry

    async def test_merge_reassigns_catalog_links(self, db, monkeypatch):
        """Regression: merging into a canonical artist must move catalog_artists
        instead of orphaning them — leaving the row behind made the ORM try to
        NULL the PK column artist_id → AssertionError → HTTP 500."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select

        self._stub_httpx(monkeypatch)

        dup = Artist(name="Dup Name", normalized_name="dup name")
        canonical = Artist(
            name="Canonical", normalized_name="canonical", deezer_id="777"
        )
        db.add_all([dup, canonical])
        await db.flush()

        entry = await self._catalog_entry(db, "dup|track")
        db.add(CatalogArtist(catalog_id=entry.id, artist_id=dup.id, role="main"))
        await db.commit()
        dup_id = dup.id

        result = await artist_service.link_to_deezer(db, dup_id, "777")

        assert result["merged"] is True
        assert result["id"] == canonical.id
        # The old artist is gone (no crash), the catalog link now points to canonical.
        assert (await db.get(Artist, dup_id)) is None
        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].artist_id == canonical.id

    async def test_merge_dedups_shared_catalog_link(self, db, monkeypatch):
        """When both artists already link the same track, the duplicate is
        dropped (composite PK) and a single link to canonical remains."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select

        self._stub_httpx(monkeypatch)

        dup = Artist(name="Dup2", normalized_name="dup2")
        canonical = Artist(name="Canon2", normalized_name="canon2", deezer_id="888")
        db.add_all([dup, canonical])
        await db.flush()

        entry = await self._catalog_entry(db, "shared|track")
        db.add_all([
            CatalogArtist(catalog_id=entry.id, artist_id=dup.id, role="main"),
            CatalogArtist(catalog_id=entry.id, artist_id=canonical.id, role="main"),
        ])
        await db.commit()
        dup_id = dup.id

        result = await artist_service.link_to_deezer(db, dup_id, "888")

        assert result["merged"] is True
        assert (await db.get(Artist, dup_id)) is None
        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].artist_id == canonical.id

    async def test_merge_survives_preloaded_catalog_links(self, db, monkeypatch):
        """Regression: even when the artist's catalog_links collection is already
        loaded in the session, deleting the merged artist must not try to NULL the
        composite-PK artist_id. passive_deletes=True on the relationship makes the
        ORM defer to the DB ON DELETE CASCADE instead of blanking the PK (500)."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select

        self._stub_httpx(monkeypatch)

        dup = Artist(name="DupPre", normalized_name="duppre")
        canonical = Artist(name="CanonPre", normalized_name="canonpre", deezer_id="999")
        db.add_all([dup, canonical])
        await db.flush()

        entry = await self._catalog_entry(db, "pre|track")
        db.add(CatalogArtist(catalog_id=entry.id, artist_id=dup.id, role="main"))
        await db.commit()
        dup_id = dup.id

        # Force the relationship into the session identity map BEFORE the merge —
        # this is what the bulk-reassign guard alone does not neutralize.
        preloaded = (
            await db.execute(select(Artist).where(Artist.id == dup_id))
        ).scalar_one()
        await db.refresh(preloaded, ["catalog_links"])
        assert len(preloaded.catalog_links) == 1

        result = await artist_service.link_to_deezer(db, dup_id, "999")

        assert result["merged"] is True
        assert (await db.get(Artist, dup_id)) is None
        links = (
            await db.execute(
                select(CatalogArtist).where(CatalogArtist.catalog_id == entry.id)
            )
        ).scalars().all()
        assert len(links) == 1
        assert links[0].artist_id == canonical.id


class TestResolveFlag:
    async def test_raises_lookup_error_for_missing_flag(self, db):
        with pytest.raises(LookupError):
            await artist_service.resolve_flag(db, 9999999, "approve")


class TestResolveFlagSplitDisposal:
    """N2.a — on a manual split the combined row must be disposed of and its
    catalog links fanned out to both tokens."""

    @staticmethod
    async def _catalog_entry(db, artist, key):
        from datetime import datetime, timezone

        from models import CatalogEntry

        entry = CatalogEntry(
            title=f"Track {key}",
            artist=artist,
            normalized_key=key,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)
        await db.flush()
        return entry

    @staticmethod
    def _flag(raw, tokens):
        from datetime import datetime, timezone

        from models import ArtistFlag

        now = datetime.now(timezone.utc)
        return ArtistFlag(
            raw_artist_string=raw,
            reason="manual",
            tokens=tokens,
            deezer_ids={},
            status="pending",
            created_at=now,
            updated_at=now,
        )

    async def test_disposes_combined_and_links_both_tokens(self, db):
        from models import Artist, CatalogArtist
        from sqlalchemy import select
        from utils import normalize

        combined = Artist(name="A | B", normalized_name=normalize("A | B"))
        db.add(combined)
        await db.flush()
        entry = await self._catalog_entry(db, "A | B", "a | b|track")
        db.add(
            CatalogArtist(
                catalog_id=entry.id, artist_id=combined.id, role="primary", position=0
            )
        )
        flag = self._flag("A | B", ["A", "B"])
        db.add(flag)
        await db.commit()
        combined_id, entry_id = combined.id, entry.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert result.status == "validated"
        assert len(result.resolved_artist_ids) == 2
        # Combined row is gone — no 500, no PK blank-out.
        assert (await db.get(Artist, combined_id)) is None
        # Both tokens now link the catalog row.
        linked = set(
            (
                await db.execute(
                    select(CatalogArtist.artist_id).where(
                        CatalogArtist.catalog_id == entry_id
                    )
                )
            ).scalars().all()
        )
        assert set(result.resolved_artist_ids).issubset(linked)

    async def test_fanout_covers_nonexact_rows_preserving_role_position(self, db):
        """The fan-out is driven by the combined row's REAL links, so it reaches
        catalog rows whose `artist` string differs (casing) from the flag —
        which the exact-string relink cannot — and preserves role/position."""
        from models import Artist, CatalogArtist
        from sqlalchemy import select
        from utils import normalize

        combined = Artist(name="A | B", normalized_name=normalize("A | B"))
        db.add(combined)
        await db.flush()
        # entry.artist ("a | b") != flag.raw_artist_string ("A | B") on casing.
        entry = await self._catalog_entry(db, "a | b", "nonexact|track")
        db.add(
            CatalogArtist(
                catalog_id=entry.id,
                artist_id=combined.id,
                role="featured",
                position=3,
            )
        )
        flag = self._flag("A | B", ["A", "B"])
        db.add(flag)
        await db.commit()
        entry_id = entry.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        rows = (
            await db.execute(
                select(
                    CatalogArtist.artist_id,
                    CatalogArtist.role,
                    CatalogArtist.position,
                ).where(
                    CatalogArtist.catalog_id == entry_id,
                    CatalogArtist.artist_id.in_(result.resolved_artist_ids),
                )
            )
        ).all()
        assert len(rows) == 2
        for _aid, role, position in rows:
            assert role == "featured"
            assert position == 3

    async def test_fanout_covers_set_links_no_orphan(self, db):
        """L5 regression — a source linked ONLY via set_artists (no catalog row,
        no exact flat-string match) must fan its set link out to every token, so
        after the split the tokens are ATTACHED (0 orphan) and the combined row
        is gone. Before L5 the set link died with the ON DELETE CASCADE and the
        deezer-linked tokens ended up with 0 catalog / 0 set (the prod orphans)."""
        from models import Artist, CatalogArtist, DJSet, SetArtist
        from sqlalchemy import select
        from utils import normalize

        combined = Artist(name="A | B", normalized_name=normalize("A | B"))
        db.add(combined)
        await db.flush()
        dj_set = DJSet(source="trackid", title="Live set")
        db.add(dj_set)
        await db.flush()
        db.add(SetArtist(set_id=dj_set.id, artist_id=combined.id, role="dj", position=2))
        flag = self._flag("A | B", ["A", "B"])
        db.add(flag)
        await db.commit()
        combined_id, set_id = combined.id, dj_set.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert result.status == "validated"
        assert len(result.resolved_artist_ids) == 2
        # Combined source row disposed of.
        assert (await db.get(Artist, combined_id)) is None
        # Both tokens inherit the set link, role/position preserved. issubset
        # (not ==) because the combined's OWN set_artists row is cleared by the
        # PG ON DELETE CASCADE, which the SQLite test harness does not enforce.
        rows = (
            await db.execute(
                select(SetArtist.artist_id, SetArtist.role, SetArtist.position).where(
                    SetArtist.set_id == set_id,
                    SetArtist.artist_id.in_(result.resolved_artist_ids),
                )
            )
        ).all()
        assert {aid for aid, _r, _p in rows} == set(result.resolved_artist_ids)
        for _aid, role, position in rows:
            assert role == "dj"
            assert position == 2
        # No token is an orphan: each holds at least one link (set or catalog).
        for tid in result.resolved_artist_ids:
            n_set = (
                await db.execute(
                    select(SetArtist.artist_id).where(SetArtist.artist_id == tid)
                )
            ).all()
            n_cat = (
                await db.execute(
                    select(CatalogArtist.artist_id).where(
                        CatalogArtist.artist_id == tid
                    )
                )
            ).all()
            assert len(n_set) + len(n_cat) > 0

    async def test_fanout_covers_both_catalog_and_set_links(self, db):
        """A source with BOTH catalog and set links whose flat `artist` string
        differs from the flag (exact relink misses it) fans BOTH out to every
        token — the catalog-only fan-out of N2.a would have dropped the set link."""
        from models import Artist, CatalogArtist, DJSet, SetArtist
        from sqlalchemy import select
        from utils import normalize

        combined = Artist(name="A | B", normalized_name=normalize("A | B"))
        db.add(combined)
        await db.flush()
        # Flat artist string differs on casing → exact relink cannot reach it.
        entry = await self._catalog_entry(db, "a | b", "both|track")
        db.add(
            CatalogArtist(
                catalog_id=entry.id, artist_id=combined.id, role="primary", position=0
            )
        )
        dj_set = DJSet(source="trackid", title="Live set")
        db.add(dj_set)
        await db.flush()
        db.add(SetArtist(set_id=dj_set.id, artist_id=combined.id, role="dj", position=1))
        flag = self._flag("A | B", ["A", "B"])
        db.add(flag)
        await db.commit()
        entry_id, set_id, combined_id = entry.id, dj_set.id, combined.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert (await db.get(Artist, combined_id)) is None
        cat_linked = set(
            (
                await db.execute(
                    select(CatalogArtist.artist_id).where(
                        CatalogArtist.catalog_id == entry_id
                    )
                )
            ).scalars().all()
        )
        set_linked = set(
            (
                await db.execute(
                    select(SetArtist.artist_id).where(SetArtist.set_id == set_id)
                )
            ).scalars().all()
        )
        assert set(result.resolved_artist_ids).issubset(cat_linked)
        assert set(result.resolved_artist_ids).issubset(set_linked)

    async def test_guard_keeps_combined_when_it_is_a_created_token(self, db):
        """If a split token resolves back to the combined row itself, the guard
        must NOT delete it (id ∈ resolved_artist_ids)."""
        from models import Artist
        from utils import normalize

        combined = Artist(name="Solo Duo", normalized_name=normalize("Solo Duo"))
        db.add(combined)
        await db.flush()
        # Degenerate split: the only token normalizes back to the combined row.
        flag = self._flag("Solo Duo", ["Solo Duo"])
        db.add(flag)
        await db.commit()
        combined_id = combined.id

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert combined_id in result.resolved_artist_ids
        assert (await db.get(Artist, combined_id)) is not None

    async def test_split_without_combined_row_is_noop(self, db):
        """No combined Artist row exists → nothing to dispose of, no crash."""
        from models import Artist
        from sqlalchemy import select

        flag = self._flag("Ghost | Phantom", ["Ghost", "Phantom"])
        db.add(flag)
        await db.commit()

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert result.status == "validated"
        assert len(result.resolved_artist_ids) == 2
        names = set(
            (await db.execute(select(Artist.name))).scalars().all()
        )
        assert {"Ghost", "Phantom"}.issubset(names)

    async def test_split_skips_deezer_id_already_held(self, db):
        """DIGGY-APP-19 — a token whose deezer_id is already held by another
        artist (accent/Unicode twin) must NOT be stamped: the next iteration's
        autoflush would raise a UniqueViolation on uq_artists_deezer_id. The
        new token is created WITHOUT the id (invariant #4); the holder keeps it."""
        from datetime import datetime, timezone

        from models import Artist, ArtistFlag
        from utils import normalize

        holder = Artist(name="Nick León", normalized_name=normalize("Nick León"))
        holder.deezer_id = "5426341"
        db.add(holder)
        await db.flush()
        holder_id = holder.id

        now = datetime.now(timezone.utc)
        flag = ArtistFlag(
            raw_artist_string="Nick Leon",
            reason="manual",
            tokens=["Nick Leon"],
            deezer_ids={"Nick Leon": "5426341"},
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(flag)
        await db.commit()

        result = await artist_service.resolve_flag(db, flag.id, "split")

        assert result.status == "validated"
        assert len(result.resolved_artist_ids) == 1
        new_id = result.resolved_artist_ids[0]
        assert new_id != holder_id
        new_artist = await db.get(Artist, new_id)
        assert new_artist.deezer_id is None
        # The existing holder keeps the id.
        assert (await db.get(Artist, holder_id)).deezer_id == "5426341"
