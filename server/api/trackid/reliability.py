"""Set reliability scoring + exclusion predicates for TrackID audiostreams (C8).

Every DJ set comes from TrackID.net community audiostreams; some carry almost no
identified music (mostly ``ID - ID`` tracks), no ``source_url`` and only the
generic TrackID placeholder cover. Those are unreliable: they should be hidden
everywhere and excluded from proximity scoring WITHOUT deleting the underlying
tracks (the ``sets.unreliable`` flag, computed at import and refreshed on every
re-import).

This module is PURE — no DB session, no network. Keeping the rule and the
exclusion predicates here means the import path, the recrawl task, the backfill
script and the read services all agree on one definition.
"""

import hashlib

# Dominant signal: share of unidentified ("ID") tracks. At or above this ratio a
# set carries too little identified music to be trusted. 0.8 = ≥80% ID tracks.
ID_RATIO_UNRELIABLE = 0.8

# TrackID serves a single default cover for audiostreams without their own
# artwork; those placeholder images are byte-identical, so they share one md5.
# Two ways to recognise the placeholder:
#   - at IMPORT, the audiostream detail's ``artworkUrl`` equals the URL below;
#   - at BACKFILL, the stored image bytes hash to the md5 below.
# Only the leading hex of the shared md5 was captured from prod, so byte matching
# is by PREFIX (see :func:`artwork_bytes_are_placeholder`).
#
# NOTE: the exact placeholder URL/md5 must be confirmed against a live TrackID
# payload / a stored placeholder image before the placeholder signal is trusted
# in prod. Until then the dominant ID-ratio signal carries the flag on its own;
# a wrong URL/md5 only means the SECONDARY placeholder signal never fires (it can
# never produce a false positive, since the secondary branch also requires a
# missing source_url).
PLACEHOLDER_ARTWORK_URL = "https://trackid.net/assets/images/no-artwork.png"
PLACEHOLDER_ARTWORK_MD5_PREFIX = "6e4c7dc9"


def is_placeholder_artwork_url(url: str | None) -> bool:
    """True if a TrackID ``artworkUrl`` points at the generic placeholder cover."""
    if not url:
        return False
    return url.strip() == PLACEHOLDER_ARTWORK_URL


def artwork_bytes_are_placeholder(data: bytes | None) -> bool:
    """True if raw image bytes are the TrackID placeholder cover.

    Matches the shared placeholder md5 by prefix (the full digest was not
    captured). Used by the backfill script, which reads the stored image bytes.
    """
    if not data:
        return False
    return hashlib.md5(data).hexdigest().startswith(PLACEHOLDER_ARTWORK_MD5_PREFIX)


def compute_set_unreliable(
    total_tracks: int,
    id_tracks: int,
    source_url: str | None,
    placeholder_artwork: bool,
) -> bool:
    """Decide whether a TrackID set is unreliable.

    Dominant signal — identification ratio: a set whose share of unidentified
    ("ID") tracks is ``>= ID_RATIO_UNRELIABLE`` carries too little real music to
    trust. A set with no tracks at all (``total_tracks <= 0``) is unreliable by
    the same token.

    Secondary signal — provenance: a missing ``source_url`` COMBINED WITH the
    generic placeholder artwork marks a set with no trustworthy origin. Either
    one alone is not enough (many legitimate sets lack one or the other).

    The three inputs are independent on purpose: the recrawl re-imports through
    ``import_audiostream``, which re-observes all three, but a caller that cannot
    re-observe the artwork can still recompute the ratio component and pass back
    the placeholder state it already knows.
    """
    if total_tracks <= 0:
        return True

    id_ratio = id_tracks / total_tracks
    if id_ratio >= ID_RATIO_UNRELIABLE:
        return True

    has_source = bool(source_url and source_url.strip())
    if not has_source and placeholder_artwork:
        return True

    return False


def set_reliable():
    """SQLAlchemy predicate keeping only reliable sets (``unreliable`` false).

    Mirrors ``catalog_service.catalog_visible`` in shape. ADD it to the existing
    roots-only filter (``parent_set_id IS NULL``) — it complements, never
    replaces it.
    """
    from models import DJSet

    return DJSet.unreliable.is_(False)


def set_reliable_sql(alias: str = "s") -> str:
    """Raw-SQL twin of :func:`set_reliable` for ``text()`` queries (genre_service).

    Returns a boolean SQL fragment scoping the sets of table ``alias`` to the
    reliable ones. ADD it to the roots-only predicate — it complements, never
    replaces it. ``IS NOT TRUE`` treats a NULL as reliable (defensive: the column
    is NOT NULL with a ``false`` default in practice).
    """
    return f"{alias}.unreliable IS NOT TRUE"
