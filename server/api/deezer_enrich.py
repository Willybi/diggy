"""
Deezer enrichment utilities for catalog entries.

Searches Deezer API by artist+title and fills:
  deezer_id, isrc, duration_ms, has_preview, has_artwork (+ cover upload).

Used by:
  - resolve_set_tracks (inline enrichment on new entries)
  - enrich_catalog Celery task (weekly backfill)
  - enrich_catalog_deezer.py one-shot script
"""

import re as _re

import httpx
import requests
from services.image_service import BUCKET_CATALOG, ImageService

DEEZER_API = "https://api.deezer.com"
RATE_LIMIT = 0.12  # seconds between requests


# Non-significant suffixes — safe to strip, they don't change the track identity
_SAFE_STRIP = _re.compile(
    r"\s*[\(\[]"
    r"\s*(?:"
    r"(?:Extended|Original|Radio|Club|Dub|Instrumental|Short|Long)(?:\s+(?:Mix|Edit|Version))?"
    r"|Album Version"
    r"|Main Mix"
    r"|Remastered(?:\s+\d{4})?"
    r"|feat\.?\s+[^)\]]*"
    r"|ft\.?\s+[^)\]]*"
    r")"
    r"\s*[\)\]]",
    _re.IGNORECASE,
)

# Significant suffixes — these identify a unique remix/edit, must NOT be stripped blindly
# e.g. "(Adam Port Edit)", "(Ferry Corsten Radio Edit)", "(CLIPZ ROLLER MIX)"
# Detection: contains a proper name (capitalized word that isn't a generic term)
_GENERIC_TERMS = {
    "mix",
    "edit",
    "remix",
    "version",
    "dub",
    "rework",
    "bootleg",
    "radio",
    "extended",
    "original",
    "club",
    "instrumental",
    "vocal",
    "short",
    "long",
    "main",
    "album",
    "remastered",
    "remaster",
}


def _is_remix_paren(content: str) -> bool:
    """True if parenthesized content names a specific remixer (significant)."""
    words = _re.findall(r"[A-Za-z]+", content.lower())
    # If it contains any word that isn't a generic mixing term, it's a named remix
    return any(w not in _GENERIC_TERMS for w in words)


def _strip_safe_suffixes(title: str) -> str | None:
    """Remove non-significant suffixes (feat, Extended Mix, Remastered, etc.)."""
    cleaned = _SAFE_STRIP.sub("", title).strip()
    # Also strip nested parens left over, e.g. outer parens wrapping a remastered tag
    cleaned = _re.sub(r"\(\s*\)", "", cleaned).strip()
    return cleaned if cleaned and cleaned != title else None


def _strip_non_remix_parens(title: str) -> str | None:
    """Remove parenthesized content ONLY if it's not a named remix/edit."""

    def _replace(m):
        content = m.group(1)
        if _is_remix_paren(content):
            return m.group(0)  # keep it
        return ""  # strip it

    cleaned = _re.sub(r"\(([^)]*)\)", _replace, title).strip()
    cleaned = _re.sub(r"\[([^\]]*)\]", _replace, cleaned).strip()
    return cleaned if cleaned and cleaned != title else None


def _first_artist(artist: str) -> str | None:
    """Extract first artist from multi-artist string."""
    for sep in [", ", " & ", " feat. ", " feat ", " ft. ", " ft ", " x ", " X "]:
        if sep in artist:
            first = artist.split(sep)[0].strip()
            if first != artist:
                return first
    return None


def search_deezer(
    artist: str | None, title: str | None, client: httpx.Client | None = None
) -> dict | None:
    """Search Deezer for a track. Returns the best match or None."""
    if not title:
        return None

    def _get(params):
        if client:
            resp = client.get(f"{DEEZER_API}/search", params=params, timeout=10)
        else:
            resp = requests.get(f"{DEEZER_API}/search", params=params, timeout=10)
        if resp.status_code != 200:
            return {}
        return resp.json()

    def _clean(s):
        """Strip parentheses/brackets that trigger Deezer 403."""
        return s.replace("(", "").replace(")", "").replace("[", "").replace("]", "")

    def _search(t, a=artist):
        clean_t = _clean(t)
        clean_a = _clean(a) if a else a
        # Try structured search first
        if clean_a:
            data = _get({"q": f'artist:"{clean_a}" track:"{clean_t}"', "limit": 1})
            hits = data.get("data", [])
            if hits:
                return hits[0]
        # Fallback: free text search
        q = f"{clean_a} {clean_t}" if clean_a else clean_t
        data = _get({"q": q, "limit": 1})
        hits = data.get("data", [])
        return hits[0] if hits else None

    # 1. Try with original title
    hit = _search(title)
    if hit:
        return hit

    # 2. Strip safe suffixes only (feat, Remastered, Extended Mix, etc.)
    #    Keeps named remixes like "(Adam Port Edit)"
    safe = _strip_safe_suffixes(title)
    if safe:
        hit = _search(safe)
        if hit:
            return hit

    # 3. Strip non-remix parens (keeps remix/edit credits, strips everything else)
    stripped = _strip_non_remix_parens(title)
    if stripped and stripped != safe:
        hit = _search(stripped)
        if hit:
            return hit

    # 4. First artist only + cleaned title (for multi-artist tracks)
    if artist:
        first = _first_artist(artist)
        if first:
            t = stripped or safe or title
            hit = _search(t, a=first)
            if hit:
                return hit

    return None


def link_catalog_artist_from_hit(session, catalog_id: int, hit: dict):
    """Link a Deezer artist from a search hit to a catalog entry via catalog_artists.

    Uses synchronous session (for Celery tasks).
    Creates the Artist if it doesn't exist, then inserts CatalogArtist link.
    """
    from models import Artist, CatalogArtist
    from sqlalchemy import select as sa_select
    from utils import normalize

    dz_artist = hit.get("artist") or {}
    artist_name = dz_artist.get("name")
    dz_artist_id = str(dz_artist.get("id", "")) if dz_artist.get("id") else None
    if not artist_name:
        return

    norm = normalize(artist_name)
    artist = session.execute(
        sa_select(Artist).where(Artist.normalized_name == norm)
    ).scalar_one_or_none()

    if not artist:
        # Check aliases
        from models import ArtistAlias

        alias = session.execute(
            sa_select(ArtistAlias).where(ArtistAlias.normalized_alias == norm)
        ).scalar_one_or_none()
        if alias:
            artist = session.get(Artist, alias.artist_id)

    if not artist:
        from datetime import datetime, timezone

        artist = Artist(
            name=artist_name,
            normalized_name=norm,
            created_at=datetime.now(timezone.utc),
        )
        if dz_artist_id:
            artist.deezer_id = dz_artist_id
        session.add(artist)
        session.flush()

    # Check if link already exists
    existing = session.execute(
        sa_select(CatalogArtist).where(
            CatalogArtist.catalog_id == catalog_id, CatalogArtist.artist_id == artist.id
        )
    ).scalar_one_or_none()

    if not existing:
        session.add(
            CatalogArtist(
                catalog_id=catalog_id,
                artist_id=artist.id,
                role="primary",
                position=0,
            )
        )



def enrich_entry(
    entry, hit: dict, s3=None, _known_isrcs: set | None = None, session=None  # s3 ignored, kept for compat
) -> bool:
    """Apply Deezer data to a CatalogEntry. Returns True if anything changed.

    Pass _known_isrcs (set of ISRCs already in DB) to avoid unique constraint violations.
    When session is provided, uses a conflict-safe SQL UPDATE for ISRC assignment.
    """
    changed = False

    deezer_id = str(hit["id"])
    if entry.deezer_id != deezer_id:
        entry.deezer_id = deezer_id
        changed = True

    isrc = hit.get("isrc")
    if isrc and not entry.isrc:
        # Skip if ISRC already used by another entry (in-memory fast check)
        if _known_isrcs is None or isrc not in _known_isrcs:
            if session is not None:
                from sqlalchemy import text

                result = session.execute(
                    text(
                        "UPDATE catalog SET isrc = :isrc "
                        "WHERE id = :id AND isrc IS NULL "
                        "AND NOT EXISTS (SELECT 1 FROM catalog WHERE isrc = :isrc)"
                    ),
                    {"isrc": isrc, "id": entry.id},
                )
                if result.rowcount > 0:
                    entry.isrc = isrc
                    changed = True
            else:
                entry.isrc = isrc
                changed = True
            if _known_isrcs is not None:
                _known_isrcs.add(isrc)

    duration_s = hit.get("duration")
    if duration_s and not entry.duration_ms:
        entry.duration_ms = duration_s * 1000
        changed = True

    has_preview = bool((hit.get("preview") or "").strip())
    if entry.has_preview != has_preview:
        entry.has_preview = has_preview
        changed = True

    # Upload cover if missing — use cover from search hit directly (no extra API call)
    if not entry.has_artwork:
        cover_url = (hit.get("album") or {}).get("cover_medium") or (
            hit.get("album") or {}
        ).get("cover_big")
        if cover_url and ImageService.upload_from_url(
            cover_url, BUCKET_CATALOG, f"{entry.id}.jpg"
        ):
            entry.has_artwork = True
            changed = True

    # Promote private → shared when Deezer confirms the track exists
    if changed and getattr(entry, "scope", None) == "private" and entry.deezer_id:
        entry.scope = "shared"
        entry.owner_id = None

    return changed
