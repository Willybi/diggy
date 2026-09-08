"""Decision CORE turning a set ``(title, channel)`` into ordered artist ids to link.

C2c-2a — the extractor (:mod:`workers.set_artist_extract`) PROPOSES artist candidate
strings; the pure helpers (:mod:`workers.set_artist_link`) RESOLVE a name against our
own artist base. This module wires them into the single async function the linker
(C2c-2b) calls to obtain the list of ``artist_id`` a set should be linked to — BASE
first, Deezer as a last resort through an INJECTED callable.

It does ZERO I/O itself: the only ``await`` is on the caller-supplied
``deezer_verify`` coroutine (a fake in tests; in prod it encapsulates the whole
Deezer path — search + the X4 ``_matching_deezer_hits`` gate + ``_resolve_or_create_
artist`` — and returns a confirmed ``artist_id`` or ``None``). No DB session, no
network, no ``SetArtist`` creation, no position assignment — that write is C2c-2b.

Invariant #4: we only link what RESOLVES. A candidate that neither resolves in the
base nor is confirmed by Deezer yields NO link — it costs recall, never precision.
"""

from typing import NamedTuple

from workers.set_artist_extract import extract_artist_candidates
from workers.set_artist_link import resolve_name_to_id, scan_known_artists


class ResolvedArtist(NamedTuple):
    """One resolved artist to link, with its provenance.

    ``artist_id`` — the confirmed base/Deezer artist id.
    ``source``    — ``"title"`` / ``"channel"`` (from the extractor) or ``"title"``
                    for a buried KNOWN artist recovered by the scan.
    ``name``      — the candidate / matched name that resolved to this id (kept for
                    logging/audit; the writer C2c-2b does not need it).
    """

    artist_id: int
    source: str
    name: str


async def resolve_link_artist_ids(title, channel, lookup, deezer_verify):
    """Resolve a set ``(title, channel)`` into an ordered, de-duplicated list of
    :class:`ResolvedArtist` to link.

    Pipeline:

      1. Extract candidates with ``extract_artist_candidates(title, channel)`` — their
         order (title before channel) and boost are preserved by construction.
      2. For EACH extractor candidate, resolve BASE FIRST via ``resolve_name_to_id``
         (free, our curated base); ONLY on a base miss fall back to
         ``artist_id = await deezer_verify(name)`` (the injected Deezer path — search +
         X4 match + get-or-create, returns a confirmed id or ``None``).
      3. Append the KNOWN artists buried in the title (``scan_known_artists``) — these
         are ALREADY resolved against the base, added directly (source ``"title"``).
      4. Collect ``(artist_id, source, name)`` in order, DROP ``None`` ids, DE-DUP by
         ``artist_id`` (first occurrence wins — a set never links the same artist
         twice; the extractor's ordered/boosted candidates therefore take precedence
         over a duplicate buried-scan match).

    Deterministic except for ``deezer_verify``; order is stable.

    :param lookup: the ``fold_key → artist_id`` map from
        :func:`workers.set_artist_link.build_artist_lookup`.
    :param deezer_verify: ``async (name: str) -> int | None`` — a confirmed artist id
        or ``None`` if not found / not confirmed.
    """
    out: list[ResolvedArtist] = []
    seen: set[int] = set()

    def _add(artist_id, source, name):
        if artist_id is None or artist_id in seen:
            return
        seen.add(artist_id)
        out.append(ResolvedArtist(artist_id=artist_id, source=source, name=name))

    # ── extractor candidates: base first, Deezer only on a base miss ──
    for cand in extract_artist_candidates(title, channel):
        artist_id = resolve_name_to_id(cand.name, lookup)
        if artist_id is None:
            artist_id = await deezer_verify(cand.name)
        _add(artist_id, cand.source, cand.name)

    # ── buried KNOWN artists (already resolved in the base) ──
    for name, artist_id in scan_known_artists(title, lookup):
        _add(artist_id, "title", name)

    return out
