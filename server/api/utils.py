import re
import unicodedata

from sqlalchemy import func, or_


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


def search_fold(s: str | None) -> str:
    """Fold a string to a canonical, search-only form: lowercased, curly quotes
    straightened, ACCENTS STRIPPED, and every run of non-alphanumeric characters
    collapsed to a single space.

    Deliberately DIFFERENT from :func:`normalize`, which keeps accents (it backs
    the identity key ``normalized_key`` and must never merge distinct texts).
    ``search_fold`` is search-only: it exists to match the SAME text spelled with
    different punctuation, quotes or accents, so it DOES strip accents
    ("Beyoncé" -> "beyonce") and turns apostrophes/dashes/pipes/@/punctuation
    into spaces. It is symmetric — applied to both the query and the stored
    ``search_text`` column, one source text folds to the same string on both
    sides.
    """
    if not s:
        return ""
    s = s.lower()
    s = s.replace("’", "'").replace("‘", "'")
    # NFKD then drop the combining marks = accent folding (accents removed).
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Any run of non-alphanumeric chars -> one space; this also collapses
    # multiple spaces. Strip the edges afterwards.
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


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


def space_insensitive_ilike(q: str, *cols):
    """Build an ``or_`` matching ``q`` against each column both verbatim AND in a
    space-collapsed "compact" form.

    Shared mirror of the X4.f/X4.g artist/catalog search fix: a stylised Deezer
    name spelled letter-by-letter ("t e s t p r e s s") is only findable by its
    collapsed spelling ("testpress"). For EACH column it ORs the plain ILIKE with
    a ``replace(col, ' ', '')`` ILIKE on ``q`` stripped of spaces. Strictly
    additive — it only ever widens the plain match, never removes a result.

    Stripping spaces before escaping is correct (a space is not a LIKE
    metacharacter); the explicit ``escape="\\\\"`` is required because SQLite has
    no default LIKE escape char (the test suite runs on SQLite).
    """
    plain = f"%{like_escape(q)}%"
    compact = f"%{like_escape(q.replace(' ', ''))}%"
    clauses = []
    for col in cols:
        clauses.append(col.ilike(plain, escape="\\"))
        clauses.append(func.replace(col, " ", "").ilike(compact, escape="\\"))
    return or_(*clauses)


def space_insensitive_contains(q: str, *texts) -> bool:
    """In-memory twin of :func:`space_insensitive_ilike` for already-materialised
    rows (the radar bi-score feed filters in Python, not SQL).

    True when ``q`` (lowercased) is a substring of at least one text, OR when
    ``q`` stripped of spaces is a substring of that text stripped of spaces.
    Mirrors the additive space-insensitive matching so the same stylised name is
    found on both surfaces. ``None``/empty texts are handled defensively.
    """
    ql = (q or "").lower()
    q_compact = ql.replace(" ", "")
    for t in texts:
        tl = (t or "").lower()
        if ql in tl or q_compact in tl.replace(" ", ""):
            return True
    return False
