"""Payload (camelCase) -> column-contract (snake_case) mapping.

The column order below is the CONTRACT shared with L1 (prod table) and L3
(importer) — it must stay byte-for-byte identical. The export (CSV/NDJSON) emits
exactly these columns in this order.

``raw_json`` is LEAN: it holds the raw item MINUS the three heavy hydration keys
(``detectionProcesses``, ``amendments``, ``audioStreamReprocesses``) that bloat
every row × 381k and are re-fetchable via the detail endpoint. Every OTHER field
survives verbatim inside ``raw_json`` (scalars + metadata: ``order``, ``duration``,
``favouriteDate``, ``isPrivate``, ``accountAudiostream``, ``canReprocess``, …), so a
listing field NOT present in the column contract is still zero-loss. Observed extra
fields at build time (2026-08-26 real payload): ``order``, ``duration``,
``favouriteDate``, ``isPrivate``, ``detectionProcesses``, ``amendments``,
``audioStreamReprocesses``, ``accountAudiostream``, ``canReprocess``.
"""

import json

# EXACT column order of the export contract (snake_case). Do NOT reorder.
COLUMNS = (
    "trackid_id",
    "slug",
    "title",
    "channel",
    "styles",
    "status",
    "is_deleted",
    "track_count",
    "duration",
    "time_hit_rate",
    "track_hit_rate",
    "processing_priority",
    "artwork_url",
    "added_on",
    "created_on",
    "added_by",
    "added_by_id",
    "audio_stream_type",
    "external_id",
    "url",
    "favourite_count",
    "like_count",
    "average_rating",
    "raw_json",
    "window_id",
)

# Contract column -> source camelCase key in the listing payload. Only the direct
# 1:1 fields; ``styles`` / ``is_deleted`` / ``raw_json`` / ``window_id`` are
# handled specially in map_item.
_SIMPLE_FIELDS = {
    "trackid_id": "id",
    "slug": "slug",
    "title": "title",
    "channel": "channel",
    "status": "status",
    "track_count": "trackCount",
    "duration": "duration",
    "time_hit_rate": "timeHitRate",
    "track_hit_rate": "trackHitRate",
    "processing_priority": "processingPriority",
    "artwork_url": "artworkUrl",
    "added_on": "addedOn",
    "created_on": "createdOn",
    "added_by": "addedBy",
    "added_by_id": "addedById",
    "audio_stream_type": "audioStreamType",
    "external_id": "externalId",
    "url": "url",
    "favourite_count": "favouriteCount",
    "like_count": "likeCount",
    "average_rating": "averageRating",
}


# Heavy per-item hydration keys stripped from ``raw_json`` (re-fetchable via the
# detail endpoint; they would bloat every staging row × 381k). Every OTHER field
# stays verbatim in ``raw_json``.
STRIP_KEYS = frozenset(
    {"detectionProcesses", "amendments", "audioStreamReprocesses"}
)


def dumps_compact(value):
    """Compact, deterministic JSON (no spaces, sorted keys, UTF-8 preserved)."""
    return json.dumps(
        value, separators=(",", ":"), ensure_ascii=False, sort_keys=True
    )


def map_item(item, window_id):
    """Map one raw listing item -> a dict keyed by the contract columns.

    ``styles`` is serialised as a compact JSON array (contract), ``raw_json``
    holds the raw item MINUS the ``STRIP_KEYS`` heavy hydration blobs (every
    other field stays verbatim — zero loss on the fields that matter),
    ``is_deleted`` is coerced to 0/1 for the SQLite mirror (the real boolean is
    preserved in ``raw_json``). ``window_id`` records the plan window this item
    was collected from.
    """
    row = {col: item.get(src) for col, src in _SIMPLE_FIELDS.items()}

    styles = item.get("styles")
    row["styles"] = dumps_compact(styles if isinstance(styles, list) else [])
    row["is_deleted"] = 1 if item.get("isDeleted") else 0
    row["raw_json"] = dumps_compact(
        {k: v for k, v in item.items() if k not in STRIP_KEYS}
    )
    row["window_id"] = window_id
    return row
