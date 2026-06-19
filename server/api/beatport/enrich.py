"""Beatport enrichment for catalog entries.

Fills: bpm, key, bpm_source, key_source, beatport_id, label, genre, release_date, artwork.

Used by:
  - enrich_catalog_beatport Celery task (weekly backfill)
"""
import logging
from datetime import date

logger = logging.getLogger(__name__)


def parse_camelot_key(bp_key: dict | None) -> str | None:
    """Convert Beatport key {camelot_number, camelot_letter} to '7A' format."""
    if not bp_key:
        return None
    num = bp_key.get("camelot_number")
    letter = bp_key.get("camelot_letter")
    if num is not None and letter:
        return f"{num}{letter}"
    return None


def enrich_from_beatport(entry, bp_track: dict, s3=None) -> bool:
    """Apply Beatport data to a CatalogEntry. Returns True if anything changed."""
    from deezer_enrich import upload_cover_from_url

    changed = False

    # Beatport ID — always set
    bp_id = str(bp_track.get("id", ""))
    if bp_id and entry.beatport_id != bp_id:
        entry.beatport_id = bp_id
        changed = True

    # BPM — Beatport is authoritative for electronic music
    bp_bpm = bp_track.get("bpm")
    if bp_bpm and entry.bpm_source != "beatport":
        entry.bpm = float(bp_bpm)
        entry.bpm_source = "beatport"
        changed = True

    # Key — Camelot notation
    camelot = parse_camelot_key(bp_track.get("key"))
    if camelot and entry.key_source != "beatport":
        entry.key = camelot
        entry.key_source = "beatport"
        changed = True

    # Label — fill only if missing
    label_obj = bp_track.get("label")
    if label_obj and not entry.label:
        label_name = label_obj.get("name") if isinstance(label_obj, dict) else str(label_obj)
        if label_name:
            entry.label = label_name[:255]
            changed = True

    # Genre — fill only if missing
    genre_obj = bp_track.get("genre")
    if genre_obj and not entry.genre:
        genre_name = genre_obj.get("name") if isinstance(genre_obj, dict) else str(genre_obj)
        if genre_name:
            entry.genre = genre_name[:100]
            changed = True

    # Release date — fill only if missing
    publish_date = bp_track.get("publish_date")
    if publish_date and not entry.release_date:
        try:
            entry.release_date = date.fromisoformat(str(publish_date)[:10])
            changed = True
        except (ValueError, TypeError):
            pass

    # Artwork — only if missing
    if s3 and not entry.has_artwork:
        release = bp_track.get("release") or {}
        image = release.get("image") or {}
        image_uri = image.get("dynamic_uri")
        if image_uri:
            cover_url = image_uri.replace("{w}", "500").replace("{h}", "500")
            if upload_cover_from_url(s3, cover_url, entry.id):
                entry.has_artwork = True
                changed = True

    return changed
