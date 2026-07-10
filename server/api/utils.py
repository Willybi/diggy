import re


def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'")
    s = re.sub(r"\bft\.", "ft", s)
    s = re.sub(r"\bfeat\.", "feat", s)
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
