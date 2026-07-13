"""
Artist following service: follow/unfollow, followed list, activity feed,
seen state (users.settings["artist_activity_seen_at"]).

Services raise LookupError (404) or ValueError (400/409), never HTTPException.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

_SEEN_KEY = "artist_activity_seen_at"


async def _ensure_artist(db: AsyncSession, artist_id: int) -> None:
    from models import Artist

    result = await db.execute(select(Artist.id).where(Artist.id == artist_id))
    if result.scalar_one_or_none() is None:
        raise LookupError("Artist not found")


async def follow_artist(db: AsyncSession, user_id: int, artist_id: int) -> None:
    """Follow an artist. Idempotent: following twice is a no-op.

    Raises LookupError (404) if the artist does not exist.
    """
    from models import FollowedArtist

    await _ensure_artist(db, artist_id)

    existing = await db.execute(
        select(FollowedArtist.user_id).where(
            FollowedArtist.user_id == user_id,
            FollowedArtist.artist_id == artist_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    db.add(
        FollowedArtist(
            user_id=user_id,
            artist_id=artist_id,
            followed_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()


async def unfollow_artist(db: AsyncSession, user_id: int, artist_id: int) -> None:
    """Unfollow an artist. Idempotent: not following is a no-op.

    Raises LookupError (404) if the artist does not exist.
    """
    from models import FollowedArtist

    await _ensure_artist(db, artist_id)

    await db.execute(
        delete(FollowedArtist).where(
            FollowedArtist.user_id == user_id,
            FollowedArtist.artist_id == artist_id,
        )
    )
    await db.commit()


async def is_following(
    db: AsyncSession, user_id: int | None, artist_id: int
) -> bool:
    """Whether the given user follows the artist. Guests never follow."""
    from models import FollowedArtist

    if user_id is None:
        return False
    result = await db.execute(
        select(FollowedArtist.user_id).where(
            FollowedArtist.user_id == user_id,
            FollowedArtist.artist_id == artist_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def list_followed(db: AsyncSession, user_id: int):
    """Artists followed by the user, most recently followed first."""
    from models import Artist, FollowedArtist
    from schemas import FollowedArtistOut, FollowingListResponse

    result = await db.execute(
        select(
            FollowedArtist.artist_id,
            Artist.name,
            Artist.has_artwork,
            FollowedArtist.followed_at,
        )
        .join(Artist, Artist.id == FollowedArtist.artist_id)
        .where(FollowedArtist.user_id == user_id)
        .order_by(FollowedArtist.followed_at.desc())
    )
    items = [
        FollowedArtistOut(
            artist_id=row.artist_id,
            name=row.name,
            has_artwork=bool(row.has_artwork),
            followed_at=row.followed_at,
        )
        for row in result
    ]
    return FollowingListResponse(items=items)


async def get_activity(
    db: AsyncSession, user_id: int, limit: int = 20, offset: int = 0
):
    """Activity feed of the user's followed artists, newest first.

    The response field is named `type` (frontend contract) and maps the
    DB column activity_type.

    A `release` activity whose track was crawled (C6.c v2) carries a
    `catalog_id`: the catalog entry is LEFT JOINed (through the C3 visibility
    predicate — these crawled tracks are always `shared`, so it is effectively
    always-true, but the invariant that every catalog read applies the predicate
    is honoured) so the feed can render it as a full track card (cover, preview,
    bpm/key, release age) instead of a bare external link.
    """
    from models import Artist, ArtistActivity, CatalogEntry, FollowedArtist
    from schemas import ActivityListResponse, ArtistActivityOut
    from sqlalchemy import and_

    from services.catalog_service import catalog_visible

    result = await db.execute(
        select(ArtistActivity, Artist.name, CatalogEntry)
        .join(FollowedArtist, FollowedArtist.artist_id == ArtistActivity.artist_id)
        .join(Artist, Artist.id == ArtistActivity.artist_id)
        .outerjoin(
            CatalogEntry,
            and_(
                CatalogEntry.id == ArtistActivity.catalog_id,
                catalog_visible(user_id),
            ),
        )
        .where(FollowedArtist.user_id == user_id)
        .order_by(ArtistActivity.detected_at.desc(), ArtistActivity.id.desc())
        .offset(offset)
        .limit(limit)
    )
    items = [
        ArtistActivityOut(
            id=activity.id,
            artist_id=activity.artist_id,
            artist_name=artist_name,
            type=activity.activity_type,
            source=activity.source,
            title=activity.title,
            external_url=activity.external_url,
            catalog_id=activity.catalog_id,
            set_id=activity.set_id,
            detected_at=activity.detected_at,
            payload=activity.payload,
            has_artwork=bool(cat.has_artwork) if cat is not None else False,
            has_preview=bool(cat.has_preview) if cat is not None else False,
            bpm=cat.bpm if cat is not None else None,
            key=cat.key if cat is not None else None,
            duration_ms=cat.duration_ms if cat is not None else None,
            artist=cat.artist if cat is not None else None,
            release_date=cat.release_date if cat is not None else None,
        )
        for activity, artist_name, cat in result.all()
    ]
    return ActivityListResponse(items=items)


async def new_count(db: AsyncSession, user_id: int):
    """Count activities newer than the user's seen marker (all if unset)."""
    from models import ArtistActivity, FollowedArtist, User
    from schemas import NewCountResponse

    settings_result = await db.execute(
        select(User.settings).where(User.id == user_id)
    )
    settings = settings_result.scalar_one_or_none() or {}
    seen_at = None
    raw = settings.get(_SEEN_KEY)
    if raw:
        try:
            seen_at = datetime.fromisoformat(raw)
        except ValueError:
            seen_at = None

    q = (
        select(func.count())
        .select_from(ArtistActivity)
        .join(FollowedArtist, FollowedArtist.artist_id == ArtistActivity.artist_id)
        .where(FollowedArtist.user_id == user_id)
    )
    if seen_at is not None:
        q = q.where(ArtistActivity.detected_at > seen_at)
    result = await db.execute(q)
    return NewCountResponse(count=result.scalar() or 0)


async def mark_seen(db: AsyncSession, user_id: int) -> None:
    """Stamp users.settings["artist_activity_seen_at"] with now (ISO 8601 UTC)."""
    from models import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise LookupError("User not found")

    # JSON column: reassign the whole dict, in-place mutation is not tracked
    user.settings = {
        **(user.settings or {}),
        _SEEN_KEY: datetime.now(timezone.utc).isoformat(),
    }
    await db.commit()
