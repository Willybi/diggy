"""Pure helpers for the ISRC entry block (no I/O, no session).

WHY — an audit (2026-11, ``docs/audits/2026-11/donnees-indesirables.md`` §7.2/§9.3)
measured that whole ISRC blocks owned by distributor "farms" (prefixes ``GXLE``,
``GXLF``, ``KRB92``: ~10,600 catalog rows, NONE of them ever played in a DJ set)
flood the catalog through the two uncorroborated Deezer entry points: the release
watch (``workers.tasks.artists._crawl_track``) and the discography backfill
(``server/api/scripts/import_discography.py``). These helpers let those two points
refuse to CREATE a new catalog row whose ISRC starts with a blocked prefix. They
never touch an existing row (an existing row may be corroborated by a set, a
library or a playlist — the reversible masking of the existing stock is a separate
OPS script).

The block is DELIBERATELY narrow: broader registrant prefixes such as ``QT*`` /
``QZ*`` (self-distribution registrants) are NOT listed, because they also host
genuine artists — blocking them would drop real music (invariant #4: when unsure,
do nothing).

Configuration: env ``CATALOG_ISRC_BLOCKED_PREFIXES`` — comma-separated, spaces
tolerated, case-insensitive; default ``"GXLE,GXLF,KRB92"``; an EMPTY value disables
the block entirely. Read at call time (cheap), so a test or an ``.env`` change needs
no import-time trick.

Importable from the worker, the API and the ops scripts alike (stdlib only).
"""

import os

ENV_VAR = "CATALOG_ISRC_BLOCKED_PREFIXES"
DEFAULT_BLOCKED_PREFIXES = "GXLE,GXLF,KRB92"


def blocked_prefixes():
    """Return the configured blocked ISRC prefixes as an upper-cased tuple.

    Unset env → the default list; set-but-empty (or only commas/spaces) → ``()``
    (no blocking at all).
    """
    raw = os.environ.get(ENV_VAR)
    if raw is None:
        raw = DEFAULT_BLOCKED_PREFIXES
    return tuple(p.strip().upper() for p in raw.split(",") if p.strip())


def is_blocked_isrc(isrc, prefixes=None):
    """True when ``isrc`` starts with one of the blocked prefixes.

    ``None`` / empty / non-string → False (no ISRC = nothing to judge). Compared in
    upper case, surrounding whitespace ignored. ``prefixes`` overrides the env
    lookup (an iterable of prefixes, any case).
    """
    if not isinstance(isrc, str):
        return False
    value = isrc.strip().upper()
    if not value:
        return False
    if prefixes is None:
        prefixes = blocked_prefixes()
    else:
        prefixes = tuple(p.strip().upper() for p in prefixes if p and p.strip())
    return bool(prefixes) and value.startswith(prefixes)
