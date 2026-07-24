import re
import unicodedata


def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"\bft\.", "ft", s)
    s = re.sub(r"\bfeat\.", "feat", s)
    # NFC unifies the byte representations of the SAME text: precomposed "\u00eb"
    # (U+00EB) and decomposed "e" + U+0308 (NFD, as produced by Rekordbox macOS
    # exports) fold to one identity key, killing composition-only duplicates.
    # Safe because NFC never merges two distinct texts. It deliberately does NOT
    # strip accents (no accent-insensitive folding): that would collapse
    # distinct catalog `normalized_key`s and violate the "err toward separation"
    # invariant. So "Le\u00f3n" and "Leon" stay separate keys.
    s = unicodedata.normalize("NFC", s)
    return s


def make_normalized_key(title: str, artist: str | None) -> str:
    return normalize(title) + " - " + normalize(artist or "")


def like_escape(value: str) -> str:
    """Escape SQL LIKE metacharacters so `value` matches literally.

    Backslash must be escaped first (it is the escape character itself).
    Callers must declare the escape char explicitly (`.ilike(..., escape="\\\\")`
    or `ESCAPE '\\'` in raw SQL): SQLite has no default LIKE escape character,
    unlike PostgreSQL, and tests run on SQLite.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
