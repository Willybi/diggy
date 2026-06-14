"""
Deezer enrichment utilities for catalog entries.

Searches Deezer API by artist+title and fills:
  deezer_id, isrc, duration_ms, has_preview, has_artwork (+ cover upload).

Used by:
  - resolve_set_tracks (inline enrichment on new entries)
  - enrich_catalog Celery task (weekly backfill)
  - enrich_catalog_deezer.py one-shot script
"""
import os
import tempfile
import time

import boto3
import httpx
import requests
from botocore.client import Config

DEEZER_API = "https://api.deezer.com"
RATE_LIMIT = 0.12  # seconds between requests

MINIO_URL = os.environ.get("MINIO_URL", "http://minio:9000")
MINIO_USER = os.environ.get("MINIO_USER", "")
MINIO_PASSWORD = os.environ.get("MINIO_PASSWORD", "")
BUCKET = "catalog-artworks"


def _get_s3():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_URL,
        aws_access_key_id=MINIO_USER,
        aws_secret_access_key=MINIO_PASSWORD,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _ensure_bucket(s3):
    existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if BUCKET not in existing:
        s3.create_bucket(Bucket=BUCKET)
        s3.put_bucket_policy(
            Bucket=BUCKET,
            Policy=(
                f'{{"Version":"2012-10-17","Statement":[{{"Effect":"Allow",'
                f'"Principal":"*","Action":"s3:GetObject",'
                f'"Resource":"arn:aws:s3:::{BUCKET}/*"}}]}}'
            ),
        )


import re as _re

# Non-significant suffixes — safe to strip, they don't change the track identity
_SAFE_STRIP = _re.compile(
    r'\s*[\(\[]'
    r'\s*(?:'
    r'(?:Extended|Original|Radio|Club|Dub|Instrumental|Short|Long)(?:\s+(?:Mix|Edit|Version))?'
    r'|Album Version'
    r'|Main Mix'
    r'|Remastered(?:\s+\d{4})?'
    r'|feat\.?\s+[^)\]]*'
    r'|ft\.?\s+[^)\]]*'
    r')'
    r'\s*[\)\]]',
    _re.IGNORECASE,
)

# Significant suffixes — these identify a unique remix/edit, must NOT be stripped blindly
# e.g. "(Adam Port Edit)", "(Ferry Corsten Radio Edit)", "(CLIPZ ROLLER MIX)"
# Detection: contains a proper name (capitalized word that isn't a generic term)
_GENERIC_TERMS = {
    'mix', 'edit', 'remix', 'version', 'dub', 'rework', 'bootleg',
    'radio', 'extended', 'original', 'club', 'instrumental', 'vocal',
    'short', 'long', 'main', 'album', 'remastered', 'remaster',
}


def _is_remix_paren(content: str) -> bool:
    """True if parenthesized content names a specific remixer (significant)."""
    words = _re.findall(r'[A-Za-z]+', content.lower())
    # If it contains any word that isn't a generic mixing term, it's a named remix
    return any(w not in _GENERIC_TERMS for w in words)


def _strip_safe_suffixes(title: str) -> str | None:
    """Remove non-significant suffixes (feat, Extended Mix, Remastered, etc.)."""
    cleaned = _SAFE_STRIP.sub('', title).strip()
    # Also strip nested parens left over, e.g. outer parens wrapping a remastered tag
    cleaned = _re.sub(r'\(\s*\)', '', cleaned).strip()
    return cleaned if cleaned and cleaned != title else None


def _strip_non_remix_parens(title: str) -> str | None:
    """Remove parenthesized content ONLY if it's not a named remix/edit."""
    def _replace(m):
        content = m.group(1)
        if _is_remix_paren(content):
            return m.group(0)  # keep it
        return ''  # strip it
    cleaned = _re.sub(r'\(([^)]*)\)', _replace, title).strip()
    cleaned = _re.sub(r'\[([^\]]*)\]', _replace, cleaned).strip()
    return cleaned if cleaned and cleaned != title else None


def _first_artist(artist: str) -> str | None:
    """Extract first artist from multi-artist string."""
    for sep in [', ', ' & ', ' feat. ', ' feat ', ' ft. ', ' ft ', ' x ', ' X ']:
        if sep in artist:
            first = artist.split(sep)[0].strip()
            if first != artist:
                return first
    return None


def search_deezer(artist: str | None, title: str | None, client: httpx.Client | None = None) -> dict | None:
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
        return s.replace('(', '').replace(')', '').replace('[', '').replace(']', '')

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


def upload_cover_from_url(s3, cover_url: str, catalog_id: int) -> bool:
    """Download cover image and upload to MinIO. Returns True on success."""
    if not cover_url:
        return False
    try:
        img_resp = requests.get(cover_url, timeout=15)
        img_resp.raise_for_status()
        if len(img_resp.content) < 1000:  # skip placeholder images
            return False

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(img_resp.content)
            tmp = f.name
        try:
            s3.upload_file(tmp, BUCKET, f"{catalog_id}.jpg",
                           ExtraArgs={"ContentType": "image/jpeg"})
        finally:
            os.unlink(tmp)
        return True
    except Exception:
        return False


def enrich_entry(entry, hit: dict, s3=None, _known_isrcs: set | None = None) -> bool:
    """Apply Deezer data to a CatalogEntry. Returns True if anything changed.

    Pass _known_isrcs (set of ISRCs already in DB) to avoid unique constraint violations.
    """
    changed = False

    deezer_id = str(hit["id"])
    if entry.deezer_id != deezer_id:
        entry.deezer_id = deezer_id
        changed = True

    isrc = hit.get("isrc")
    if isrc and not entry.isrc:
        # Skip if ISRC already used by another entry
        if _known_isrcs is None or isrc not in _known_isrcs:
            entry.isrc = isrc
            if _known_isrcs is not None:
                _known_isrcs.add(isrc)
            changed = True

    duration_s = hit.get("duration")
    if duration_s and not entry.duration_ms:
        entry.duration_ms = duration_s * 1000
        changed = True

    has_preview = bool((hit.get("preview") or "").strip())
    if entry.has_preview != has_preview:
        entry.has_preview = has_preview
        changed = True

    # Upload cover if missing — use cover from search hit directly (no extra API call)
    if s3 and not entry.has_artwork:
        cover_url = (hit.get("album") or {}).get("cover_medium") or (hit.get("album") or {}).get("cover_big")
        if upload_cover_from_url(s3, cover_url, entry.id):
            entry.has_artwork = True
            changed = True

    return changed
