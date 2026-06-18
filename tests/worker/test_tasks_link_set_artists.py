"""
Tests for link_set_artists core logic.
Replicates the matching algorithm without Celery/external DB.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Artist, ArtistAlias, DJSet, SetArtist
from utils import normalize


def _link_set_artists(session):
    """Replicate core logic of link_set_artists task."""
    # Build lookup: normalized name/alias -> artist_id
    norm_to_id = {}
    for a in session.execute(select(Artist)).scalars().all():
        norm_to_id[normalize(a.name)] = a.id
    for al in session.execute(select(ArtistAlias)).scalars().all():
        if al.normalized_alias not in norm_to_id:
            norm_to_id[al.normalized_alias] = al.artist_id

    sorted_names = sorted(norm_to_id.keys(), key=len, reverse=True)

    sets = session.execute(select(DJSet)).scalars().all()
    linked = 0
    skipped = 0

    for dj_set in sets:
        title = dj_set.title or ""
        title_lower = title.lower()
        is_b2b = "b2b" in title_lower

        matched_ids = set()
        title_norm = normalize(title)
        title_norm_clean = title_norm.replace("_", " ")

        for norm_name in sorted_names:
            if len(norm_name) < 3:
                continue
            if norm_name in title_norm or norm_name in title_norm_clean:
                aid = norm_to_id[norm_name]
                if aid not in matched_ids:
                    matched_ids.add(aid)

        existing = {
            r[0] for r in session.execute(
                select(SetArtist.artist_id).where(SetArtist.set_id == dj_set.id)
            ).all()
        }

        for aid in matched_ids:
            if aid in existing:
                skipped += 1
                continue
            role = "b2b" if is_b2b else "dj"
            session.add(SetArtist(set_id=dj_set.id, artist_id=aid, role=role, position=0))
            linked += 1

        session.commit()

    return {"linked": linked, "skipped": skipped}


class TestLinkSetArtists:
    def test_matches_artist_in_title(self, sync_session):
        s = sync_session
        a = Artist(name="ANNA", normalized_name="anna")
        s.add(a)
        dj = DJSet(source="trackid", title="ANNA at Boiler Room")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 1

        sa = s.execute(select(SetArtist)).scalar_one()
        assert sa.artist_id == a.id
        assert sa.role == "dj"

    def test_b2b_role(self, sync_session):
        s = sync_session
        a1 = Artist(name="CamelPhat", normalized_name="camelphat")
        a2 = Artist(name="Solardo", normalized_name="solardo")
        s.add_all([a1, a2])
        dj = DJSet(source="trackid", title="CamelPhat B2B Solardo")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 2

        links = s.execute(select(SetArtist)).scalars().all()
        assert all(l.role == "b2b" for l in links)

    def test_skips_short_names(self, sync_session):
        s = sync_session
        a = Artist(name="DJ", normalized_name="dj")
        s.add(a)
        dj = DJSet(source="trackid", title="DJ ANNA at Club")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        # "dj" is < 3 chars, should be skipped
        assert result["linked"] == 0

    def test_skips_existing_links(self, sync_session):
        s = sync_session
        a = Artist(name="ANNA", normalized_name="anna")
        s.add(a)
        dj = DJSet(source="trackid", title="ANNA at Club")
        s.add(dj)
        s.flush()
        s.add(SetArtist(set_id=dj.id, artist_id=a.id, role="dj", position=0))
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 0
        assert result["skipped"] == 1

    def test_matches_via_alias(self, sync_session):
        s = sync_session
        a = Artist(name="CamelPhat", normalized_name="camelphat")
        s.add(a)
        s.flush()
        s.add(ArtistAlias(artist_id=a.id, alias="Camel Phat", normalized_alias="camel phat"))
        dj = DJSet(source="trackid", title="Camel Phat live at Ushuaia")
        s.add(dj)
        s.commit()

        result = _link_set_artists(s)
        assert result["linked"] == 1

        sa = s.execute(select(SetArtist)).scalar_one()
        assert sa.artist_id == a.id
