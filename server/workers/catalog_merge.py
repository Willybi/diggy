"""Catalog de-duplication primitive (sync worker context).

``catalog`` is the central hub every other table points to via ``catalog_id``.
Ingestion dedups on ``normalized_key``/``isrc`` but never on the platform ids
(``deezer_id``/``beatport_id``), so the same track can land twice. This module
folds a duplicate ("loser") row into the row we keep ("canonical"):

    canonical = pick_canonical(duplicate_rows)
    for loser in duplicate_rows:
        if loser is not canonical:
            merge_catalog_entries(session, canonical.id, loser.id)

Every table referencing ``catalog.id`` is repointed with bulk UPDATE/DELETE
(no ORM relationship cascade) BEFORE the loser is removed — ``user_tracks`` is
``ON DELETE RESTRICT`` so the delete would otherwise fail. This lot only ships
the primitive and its tests: no enrichment integration, no cleanup script.
"""

import re

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session


class CatalogEntryMerged(Exception):
    """Signal that the entry being enriched duplicated an existing catalog row.

    Raised by an enrichment function (X1/L2 prevention) when it is about to
    stamp a platform id (``deezer_id``/``beatport_id``) that another catalog row
    already carries. The duplicate ("loser") has ALREADY been folded into the
    pre-existing ("canonical") row via :func:`merge_catalog_entries`;
    ``surviving_id`` is the canonical row that remains. The caller must stop
    post-processing the now-deleted entry (no ``_mark_searched``, artist link,
    ``artist_activity`` creation, ...) — the metadata is already unified and the
    canonical already carries the id, so it will not be re-selected.
    """

    def __init__(self, surviving_id: int):
        self.surviving_id = surviving_id
        super().__init__(f"catalog entry folded into canonical {surviving_id}")


# ── Safe identity predicate ────────────────────────────────────────────────
#
# Sharing a platform id (deezer_id/beatport_id) does NOT mean two catalog rows
# are the same recording: Deezer search returns hits[0] unchecked, so a REMIX
# inherits the ORIGINAL's deezer_id; the Beatport release fallback stamps one
# beatport_id on EVERY track of an EP. Merging on the platform id alone would
# destroy those distinct versions (project invariant #4: always err toward
# separation). ``same_track`` is the guard: it confirms identity from the ISRC
# (recording identity) or, absent one, from a conservative remix-aware title
# comparison. When in doubt it returns False — a missed dup is cheap storage
# debt, a bad merge is data corruption.

# Non-distinctive noise removed from a title (it never changes which recording
# the title names): featured-artist credits, and the "(original mix)"/"(original)"
# default-version marker. Every OTHER parenthesised marker (remix, edit, dub,
# a non-original mix, version, extended, bootleg, ...) is PRESERVED.
_RE_FEAT = re.compile(
    r"\s*[\(\[]\s*(?:featuring|feat|ft)\b\.?\s[^)\]]*[\)\]]", re.IGNORECASE
)
# The bare-credit tail stops at the first "(" or "[": a feat credit runs to the
# end of the title UNLESS a parenthesised version marker follows it, which must
# be preserved (else "Song feat. X (Club Mix)" and "… (Radio Edit)" would both
# collapse to "song" and merge two distinct versions — invariant #4).
_RE_FEAT_BARE = re.compile(r"\s+(?:featuring|feat|ft)\b\.?\s[^(\[]*$", re.IGNORECASE)
_RE_ORIGINAL = re.compile(
    r"\s*[\(\[]\s*original(?:\s+mix)?\s*[\)\]]\s*$", re.IGNORECASE
)
_RE_TITLE_SPACES = re.compile(r"\s+")


def normalize_track_title(title: str) -> str:
    """Conservative, remix-aware normalization of a track title.

    Lowercases, trims and compacts internal whitespace, then strips ONLY the
    non-distinctive noise — "(feat. …)"/"feat. …"/"ft. …" credits and the
    trailing "(original mix)"/"(original)" marker. Any version/remix marker
    ("(… remix)", "(… edit)", "(… dub)", "(… version)", "(extended …)",
    "(… bootleg)", a non-original "(… mix)", …) is left intact so two versions
    normalise to DIFFERENT strings and never merge.

    Guiding rule (merge asymmetry): when unsure whether a marker is noise, keep
    it — over-stripping causes a bad merge (corruption); under-stripping only
    misses a duplicate (harmless storage debt).
    """
    t = (title or "").lower().strip()
    t = _RE_FEAT.sub("", t)
    t = _RE_ORIGINAL.sub("", t)
    t = _RE_FEAT_BARE.sub("", t)
    t = _RE_TITLE_SPACES.sub(" ", t).strip()
    return t


def same_track(a, b) -> bool:
    """True only if ``a`` and ``b`` are confidently the SAME recording.

    ``a`` and ``b`` are catalog rows already known to share a platform id, so
    the id is not re-compared — the point is to confirm or REFUTE the recording
    identity:

    - Both carry an ISRC → they are the same iff the ISRCs are equal. Two
      distinct ISRCs are two recordings even under one platform id (this is what
      separates the remixes of an EP that share a beatport_id).
    - Otherwise (at least one ISRC missing) → fall back to the conservative
      title comparison.
    """
    a_isrc = getattr(a, "isrc", None)
    b_isrc = getattr(b, "isrc", None)
    if a_isrc and b_isrc:
        return a_isrc == b_isrc
    return normalize_track_title(a.title) == normalize_track_title(b.title)


# Columns whose non-NULL presence signals a "more complete" catalog row. Used
# as the last-resort canonical tie-breaker before the (unique) id.
_COMPLETENESS_FIELDS = ("bpm", "key", "duration_ms", "label", "release_date")


def _completeness(entry) -> int:
    """Number of populated metadata fields on ``entry``.

    Nullable columns count when non-NULL; the two boolean flags count only when
    True (a False flag carries no information, so it must not inflate the score).
    """
    score = sum(1 for f in _COMPLETENESS_FIELDS if getattr(entry, f) is not None)
    if entry.has_artwork:
        score += 1
    if entry.has_preview:
        score += 1
    return score


def _canonical_sort_key(entry):
    """Sort key where the SMALLEST tuple is the preferred canonical row.

    Priority: ISRC present > oldest ``created_at`` (NULL sinks last) > most
    complete > lowest ``id``. ``id`` is unique so the order is total — no ties.
    """
    has_isrc = 0 if entry.isrc else 1
    # (0, ts) always sorts before (1, 0), so a NULL created_at is deprioritised
    # without ever comparing a datetime against an int.
    created = (0, entry.created_at) if entry.created_at is not None else (1, 0)
    return (has_isrc, created, -_completeness(entry), entry.id)


def pick_canonical(entries: list) -> "CatalogEntry":  # noqa: F821
    """Deterministically choose the CatalogEntry to KEEP among duplicates.

    ``entries`` are rows known to be duplicates (e.g. sharing a ``deezer_id``).
    Order: ISRC present first, then oldest, then most complete, then lowest id.
    """
    if not entries:
        raise ValueError("pick_canonical requires a non-empty list of entries")
    return min(entries, key=_canonical_sort_key)


def _latest(a, b):
    """Most recent of two nullable datetimes (either may be None)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


def _repoint_composite(session: Session, model, other_pk, canonical_id, loser_id):
    """Move rows of a ``(catalog_id, other_pk)`` composite-PK table.

    A loser row whose ``other_pk`` already exists on the canonical would collide
    on the primary key, so it is dropped; the rest are repointed in place.
    """
    session.execute(
        delete(model)
        .where(
            model.catalog_id == loser_id,
            other_pk.in_(select(other_pk).where(model.catalog_id == canonical_id)),
        )
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(model)
        .where(model.catalog_id == loser_id)
        .values(catalog_id=canonical_id)
        .execution_options(synchronize_session=False)
    )


def _repoint_simple(session: Session, model, canonical_id, loser_id):
    """Repoint a table whose ``catalog_id`` is a plain (non-PK) column."""
    session.execute(
        update(model)
        .where(model.catalog_id == loser_id)
        .values(catalog_id=canonical_id)
        .execution_options(synchronize_session=False)
    )


def merge_catalog_entries(
    session: Session, canonical_id: int, loser_id: int
) -> None:
    """Fold the ``loser_id`` catalog row into ``canonical_id`` and delete it.

    Repoints every table referencing ``catalog.id`` (real FKs plus the
    ``user_opinions`` pseudo-FK) from the loser to the canonical, unions the
    metadata onto the canonical (NULL-fill only, OR-ing the artwork/preview
    flags, keeping the richer search history and never downgrading a shared
    row), then removes the loser. All moves are bulk UPDATE/DELETE — no ORM
    cascade.

    Idempotent-safe: ``canonical_id == loser_id`` or an already-removed loser is
    a no-op. Raises ``ValueError`` if the canonical row does not exist.
    """
    from models import (
        ArtistActivity,
        CatalogArtist,
        CatalogEntry,
        CollectionItem,
        RadarTrack,
        RadarTrend,
        SetTrack,
        UserOpinion,
        UserRadarState,
        UserTrack,
    )

    if canonical_id == loser_id:
        return

    canonical = session.get(CatalogEntry, canonical_id)
    loser = session.get(CatalogEntry, loser_id)
    if loser is None:
        # Already merged/removed — nothing to do.
        return
    if canonical is None:
        raise ValueError(f"canonical catalog row {canonical_id} does not exist")

    # ── Capture the loser metadata up front. The unique columns (isrc,
    # deezer_id, beatport_id) are applied to the canonical only AFTER the loser
    # row is deleted, to avoid a transient unique-constraint violation. ──
    loser_isrc = loser.isrc
    loser_deezer_id = loser.deezer_id
    loser_beatport_id = loser.beatport_id
    loser_genres = list(loser.genres or [])
    loser_duration_ms = loser.duration_ms
    loser_label = loser.label
    loser_release_date = loser.release_date
    loser_bpm = loser.bpm
    loser_bpm_source = loser.bpm_source
    loser_key = loser.key
    loser_key_source = loser.key_source
    loser_has_artwork = bool(loser.has_artwork)
    loser_has_preview = bool(loser.has_preview)
    loser_deezer_searched_at = loser.deezer_searched_at
    loser_deezer_attempts = loser.deezer_search_attempts or 0
    loser_beatport_searched_at = loser.beatport_searched_at
    loser_beatport_attempts = loser.beatport_search_attempts or 0
    loser_scope = loser.scope
    canonical_genres = list(canonical.genres or [])

    # ── Repoint every child table. Composite-PK tables are conflict-aware. ──

    # catalog_artists (PK catalog_id+artist_id): never duplicate an artist link.
    _repoint_composite(session, CatalogArtist, CatalogArtist.artist_id, canonical_id, loser_id)

    # user_tracks (PK user_id+catalog_id, ON DELETE RESTRICT): where the same
    # user owns both rows, fill the canonical's avis/rating from the loser
    # BEFORE the colliding loser row is dropped; then move the rest.
    session.execute(
        text(
            "UPDATE user_tracks SET "
            "avis = COALESCE(avis, (SELECT l.avis FROM user_tracks l "
            "WHERE l.user_id = user_tracks.user_id AND l.catalog_id = :loser)), "
            "rating = COALESCE(rating, (SELECT l.rating FROM user_tracks l "
            "WHERE l.user_id = user_tracks.user_id AND l.catalog_id = :loser)) "
            "WHERE catalog_id = :canonical AND EXISTS "
            "(SELECT 1 FROM user_tracks l WHERE l.user_id = user_tracks.user_id "
            "AND l.catalog_id = :loser)"
        ),
        {"loser": loser_id, "canonical": canonical_id},
    )
    _repoint_composite(session, UserTrack, UserTrack.user_id, canonical_id, loser_id)

    # collection_items (PK collection_id+catalog_id): drop dup, else repoint.
    _repoint_composite(
        session, CollectionItem, CollectionItem.collection_id, canonical_id, loser_id
    )

    # user_radar_state (PK user_id+catalog_id): NOT listed in the L1 brief but a
    # real catalog_id FK (ON DELETE CASCADE) — without this repoint the loser
    # delete would cascade away (PG) / orphan (SQLite) each user's radar status.
    _repoint_composite(
        session, UserRadarState, UserRadarState.user_id, canonical_id, loser_id
    )

    # set_tracks / radar_tracks / artist_activity: plain catalog_id column.
    _repoint_simple(session, SetTrack, canonical_id, loser_id)
    _repoint_simple(session, RadarTrack, canonical_id, loser_id)
    _repoint_simple(session, ArtistActivity, canonical_id, loser_id)

    # radar_trends (PK includes catalog_id): recomputed nightly — drop, no move.
    session.execute(
        delete(RadarTrend)
        .where(RadarTrend.catalog_id == loser_id)
        .execution_options(synchronize_session=False)
    )

    # user_opinions (pseudo-FK entity_type='track'/entity_key=str(catalog_id)):
    # drop the loser opinion where the user already rated the canonical, else
    # repoint the entity_key.
    session.execute(
        delete(UserOpinion)
        .where(
            UserOpinion.entity_type == "track",
            UserOpinion.entity_key == str(loser_id),
            UserOpinion.user_id.in_(
                select(UserOpinion.user_id).where(
                    UserOpinion.entity_type == "track",
                    UserOpinion.entity_key == str(canonical_id),
                )
            ),
        )
        .execution_options(synchronize_session=False)
    )
    session.execute(
        update(UserOpinion)
        .where(
            UserOpinion.entity_type == "track",
            UserOpinion.entity_key == str(loser_id),
        )
        .values(entity_key=str(canonical_id))
        .execution_options(synchronize_session=False)
    )

    # ── Union the (non-unique) metadata onto the canonical, NULL-fill only ──

    merged_genres = list(canonical_genres)
    for g in loser_genres:
        if g not in merged_genres:
            merged_genres.append(g)
    if merged_genres != canonical_genres:
        canonical.genres = merged_genres

    if canonical.duration_ms is None and loser_duration_ms is not None:
        canonical.duration_ms = loser_duration_ms
    if canonical.label is None and loser_label is not None:
        canonical.label = loser_label
    if canonical.release_date is None and loser_release_date is not None:
        canonical.release_date = loser_release_date

    # Beatport is the BPM/key authority: only fill when the canonical has none,
    # so an existing value/source is never overwritten. Carry the provenance.
    if canonical.bpm is None and loser_bpm is not None:
        canonical.bpm = loser_bpm
        canonical.bpm_source = loser_bpm_source
    if canonical.key is None and loser_key is not None:
        canonical.key = loser_key
        canonical.key_source = loser_key_source

    # has_artwork / has_preview: logical OR (either row having it wins).
    if loser_has_artwork and not canonical.has_artwork:
        canonical.has_artwork = True
    if loser_has_preview and not canonical.has_preview:
        canonical.has_preview = True

    # Keep the richer search history so the merged row is not re-searched.
    canonical.deezer_search_attempts = max(
        canonical.deezer_search_attempts or 0, loser_deezer_attempts
    )
    canonical.deezer_searched_at = _latest(
        canonical.deezer_searched_at, loser_deezer_searched_at
    )
    canonical.beatport_search_attempts = max(
        canonical.beatport_search_attempts or 0, loser_beatport_attempts
    )
    canonical.beatport_searched_at = _latest(
        canonical.beatport_searched_at, loser_beatport_searched_at
    )

    # Never downgrade a shared row to private.
    if loser_scope == "shared" or canonical.scope == "shared":
        canonical.scope = "shared"
        canonical.owner_id = None

    # ── Remove the loser, then move its unique columns onto the canonical
    # (done last so the unique constraints never see a transient duplicate) ──
    session.expunge(loser)
    session.execute(
        delete(CatalogEntry)
        .where(CatalogEntry.id == loser_id)
        .execution_options(synchronize_session=False)
    )

    if canonical.isrc is None and loser_isrc is not None:
        canonical.isrc = loser_isrc
    if canonical.deezer_id is None and loser_deezer_id is not None:
        canonical.deezer_id = loser_deezer_id
    if canonical.beatport_id is None and loser_beatport_id is not None:
        canonical.beatport_id = loser_beatport_id

    session.flush()
