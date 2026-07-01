"""
Tests for crawl_followed_sets eligibility logic.
Replicates the filtering logic without Celery or async.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models import DJSet, SetTrack, UserSetFollow, CatalogEntry, User
from utils import make_normalized_key


def _find_eligible_sets(session):
    """Replicate the filtering logic of crawl_followed_sets."""
    followed_ids = {
        r[0] for r in session.execute(
            select(UserSetFollow.set_id).distinct()
        ).all()
    }

    if not followed_ids:
        return [], 0, 0

    sets_to_crawl = []
    skipped_complete = 0
    skipped_recent = 0

    for sid in followed_ids:
        dj_set = session.get(DJSet, sid)
        if not dj_set or dj_set.source != "trackid":
            continue

        total = session.execute(
            select(func.count(SetTrack.id)).where(SetTrack.set_id == sid)
        ).scalar() or 0
        identified = session.execute(
            select(func.count(SetTrack.id)).where(
                SetTrack.set_id == sid,
                SetTrack.is_id.is_(False),
                SetTrack.catalog_id.isnot(None),
            )
        ).scalar() or 0

        if total > 0 and identified >= total:
            skipped_complete += 1
            continue

        if dj_set.last_crawled_at:
            last = dj_set.last_crawled_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            if age_h < 12:
                skipped_recent += 1
                continue

        sets_to_crawl.append(dj_set.id)

    return sets_to_crawl, skipped_complete, skipped_recent


class TestCrawlFollowedSets:
    def _make_user(self, session):
        u = User(email="t@t.com", username="t", google_id="google-test", is_active=True)
        session.add(u)
        session.flush()
        return u

    def test_skip_complete_set(self, sync_session):
        s = sync_session
        u = self._make_user(s)

        cat = CatalogEntry(title="T", artist="A", normalized_key="t - a")
        s.add(cat)
        s.flush()

        dj = DJSet(source="trackid", title="Complete Set",
                    last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=24))
        s.add(dj)
        s.flush()
        # 1 track, fully identified
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", catalog_id=cat.id, is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()

        eligible, skipped_complete, skipped_recent = _find_eligible_sets(s)
        assert eligible == []
        assert skipped_complete == 1

    def test_skip_recent_set(self, sync_session):
        s = sync_session
        u = self._make_user(s)

        dj = DJSet(source="trackid", title="Recent Set",
                    last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=2))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()

        eligible, skipped_complete, skipped_recent = _find_eligible_sets(s)
        assert eligible == []
        assert skipped_recent == 1

    def test_crawl_eligible_set(self, sync_session):
        s = sync_session
        u = self._make_user(s)

        dj = DJSet(source="trackid", title="Eligible Set",
                    last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=24))
        s.add(dj)
        s.flush()
        # 2 tracks, 1 unresolved
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="Known", is_id=False))
        s.add(SetTrack(set_id=dj.id, position=2, raw_title="ID", is_id=True))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()

        eligible, skipped_complete, skipped_recent = _find_eligible_sets(s)
        assert len(eligible) == 1
        assert eligible[0] == dj.id
        assert skipped_complete == 0
        assert skipped_recent == 0

    def test_no_followed_sets(self, sync_session):
        s = sync_session
        eligible, sc, sr = _find_eligible_sets(s)
        assert eligible == []
        assert sc == 0
        assert sr == 0

    def test_skip_non_trackid_source(self, sync_session):
        s = sync_session
        u = self._make_user(s)

        dj = DJSet(source="manual", title="Manual Set",
                    last_crawled_at=datetime.now(timezone.utc) - timedelta(hours=24))
        s.add(dj)
        s.flush()
        s.add(SetTrack(set_id=dj.id, position=1, raw_title="T", is_id=False))
        s.add(UserSetFollow(user_id=u.id, set_id=dj.id, followed_at=datetime.now(timezone.utc)))
        s.commit()

        eligible, _, _ = _find_eligible_sets(s)
        assert eligible == []
