"""C12 scoring: turn the shadow-hydration staging into a per-set phase + priority
score, exported as NDJSON for the OPS import into prod ``trackid_index``.

This is the LOCAL counterpart of the frozen C12 scoring spec
(``docs/prompts/C12-scoring-preflight-results.md``). It reads three things — all
local, no network, no ``server`` package:

  * the shadow staging ``data/staging.db`` (written by ``shadow.py``): tables
    ``set_detail`` (one fetched set, ``http_status``) + ``tracklist`` (per-track
    ``is_id`` / ``matched`` / ``raw_artist``, matched READ-ONLY against a prod
    catalog snapshot) + the raw listing mirror ``trackid_index_staging``
    (``channel``).
  * curation snapshots: ``lib_artists_nn.txt.gz`` (one normalized library artist
    name per line), ``target_artists.txt.gz`` (``normalized_name<TAB>track_count``
    for artists of the curated/priority genres).
  * ``channels_prio.csv`` (columns ``prio,channel,sets,net_new,known,lib,
    net_new_rate``, ``prio`` in {0,1,2,3}) — the user-picked channel priority.

For each successfully-fetched set it computes a PHASE (0-3) from three signals and
emits ``{trackid_id, score, score_components}`` — one JSON object per line, in
``trackid_id`` order. Sets that fall into "reste" (no signal, unlisted channel) or
"exclu" (``prio == 0``) are NOT emitted: they are never hydrated.

Signals (per set; a "net-new" track = a listing track NOT already in the catalog,
i.e. ``tracklist`` rows with ``is_id = 0 AND matched = 0``):
  * ``has_lib``  — the set has >=1 net-new track whose ``normalize(raw_artist)`` is
    in the library snapshot.
  * ``has_g10``  — the set has >=1 net-new track whose artist has a curated-genre
    ``track_count >= GENRE_THRESHOLD`` (default 10).
  * channel priority from ``channels_prio.csv``: P1/P2/P3, or "reste" (channel
    absent), or "exclu" (``prio == 0``).

Phase (first matching rule wins):
  exclu                         -> NOT emitted
  has_lib                       -> phase 0  (library)
  P1  OR  (P2 AND has_g10)      -> phase 1  (core / priority channel)
  has_g10                       -> phase 2  (curated-genre artist)
  P2 OR P3                      -> phase 3  (channel discovery)
  otherwise (reste, no artist)  -> NOT emitted

``normalize`` is imported from ``shadow`` (single source of truth, prod-faithful).

Standalone, deterministic, idempotent (re-running overwrites the NDJSON), no
network, no prod connection. Writing into prod ``trackid_index`` is the OPS import
(a different lot), explicitly OUT OF SCOPE here. Run:  python score.py --help
"""

import argparse
import csv
import gzip
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shadow import normalize  # noqa: E402

# --- tunable constants (override via argv and/or env) ----------------------
DEFAULT_GENRE_THRESHOLD = 10          # env C12_GENRE_THRESHOLD / --genre-threshold
DEFAULT_PHASE_SCORES = {              # env C12_SCORE_PHASE0..3 ; higher = hydrated first
    0: 90.0,
    1: 80.0,
    2: 70.0,
    3: 60.0,
}
# Intra-phase tie-break: richer sets (more distinct net-new tracks) sort first
# WITHIN their phase. Bonus in [0, BONUS_SPAN) with BONUS_SPAN < the 10-point gap
# between phases, so it never crosses a phase band (phase0 in [90,99), etc.).
DEFAULT_BONUS_CAP = 30                 # env C12_BONUS_CAP ; net_new_count saturation
DEFAULT_BONUS_SPAN = 9.0               # env C12_BONUS_SPAN ; max bonus (exclusive)


def load_phase_scores():
    """Phase->score map, each phase overridable by env ``C12_SCORE_PHASE{n}``."""
    scores = dict(DEFAULT_PHASE_SCORES)
    for phase in scores:
        override = os.environ.get(f"C12_SCORE_PHASE{phase}")
        if override is not None:
            scores[phase] = float(override)
    return scores


def default_genre_threshold():
    return int(os.environ.get("C12_GENRE_THRESHOLD", DEFAULT_GENRE_THRESHOLD))


def load_bonus_params():
    """``(cap, span)`` for the intra-phase net-new tie-break bonus, env-overridable."""
    cap = int(os.environ.get("C12_BONUS_CAP", DEFAULT_BONUS_CAP))
    span = float(os.environ.get("C12_BONUS_SPAN", DEFAULT_BONUS_SPAN))
    return cap, span


def net_new_bonus(net_new_count, cap, span):
    """Bonus in ``[0, span)`` growing with distinct net-new tracks, saturating at
    ``cap``. Kept strictly below ``span`` (< the 10-point phase gap) so a set can
    never be pushed out of its phase band."""
    if cap <= 0:
        return 0.0
    return min(net_new_count, cap) / cap * span


# --- curation loaders ------------------------------------------------------
def _open_text(path):
    return gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(
        path, "rt", encoding="utf-8"
    )


def load_lib_artists(path):
    """Set of normalized library artist names (one per line)."""
    with _open_text(path) as f:
        return {line.rstrip("\n") for line in f if line.strip()}


def load_target_artists(path, threshold):
    """Set of normalized artist names whose curated ``track_count >= threshold``.

    File format: ``normalized_name<TAB>track_count`` per line. A name with a tab in
    it is safe (we split on the LAST tab so the count is always the final field).
    """
    qualifying = set()
    with _open_text(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or "\t" not in line:
                continue
            name, _, count = line.rpartition("\t")
            try:
                if int(count) >= threshold:
                    qualifying.add(name)
            except ValueError:
                continue
    return qualifying


def load_channel_prio(path):
    """Map ``channel -> prio (int)`` from ``channels_prio.csv`` (utf-8-sig: BOM)."""
    prio = {}
    with open(path, "rt", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            channel = row.get("channel")
            raw = row.get("prio")
            if channel is None or raw is None or raw == "":
                continue
            try:
                prio[channel] = int(raw)
            except ValueError:
                continue
    return prio


# --- pure phase assignment (see module docstring) --------------------------
def assign_phase(prio, has_lib, has_g10):
    """Return the phase (0-3) for a set, or ``None`` when it must NOT be emitted.

    ``prio`` is the channel priority (0/1/2/3) or ``None`` for an unlisted channel.
    """
    if prio == 0:                       # exclu
        return None
    if has_lib:
        return 0
    is_p1 = prio == 1
    is_p2 = prio == 2
    is_p3 = prio == 3
    if is_p1 or (is_p2 and has_g10):
        return 1
    if has_g10:
        return 2
    if is_p2 or is_p3:
        return 3
    return None                         # reste, no artist signal


def channel_prio_label(prio):
    """The ``channel_prio`` value stored in score_components: 1|2|3|'reste'."""
    return prio if prio in (1, 2, 3) else "reste"


# --- core --------------------------------------------------------------------
def _net_new_signals(conn, lib, target):
    """Per-set ``(has_lib, has_g10, net_new_count)`` folded over every net-new track.

    Streams the net-new tracks (``is_id=0 AND matched=0``) once and accumulates,
    per ``trackid_id``: the two boolean artist signals (on ``normalize(raw_artist)``)
    and the count of DISTINCT ``norm_key`` (the net-new richness tie-break). Sets
    absent from the result have no net-new track (both False, count 0).
    """
    signals = {}          # tid -> [has_lib, has_g10, set_of_distinct_norm_keys]
    cur = conn.execute(
        "SELECT trackid_id, raw_artist, norm_key FROM tracklist "
        "WHERE is_id=0 AND matched=0"
    )
    for tid, raw_artist, norm_key in cur:
        entry = signals.get(tid)
        if entry is None:
            entry = signals[tid] = [False, False, set()]
        if norm_key:
            entry[2].add(norm_key)
        nk = normalize(raw_artist or "")
        if not nk:
            continue
        if nk in lib:
            entry[0] = True
        if nk in target:
            entry[1] = True
    return {
        tid: (has_lib, has_g10, len(keys))
        for tid, (has_lib, has_g10, keys) in signals.items()
    }


def score(db_path, lib_path, target_path, channels_path, out_path,
          threshold, phase_scores, bonus_cap, bonus_span, verbose=True):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    lib = load_lib_artists(lib_path)
    target = load_target_artists(target_path, threshold)
    channel_prio = load_channel_prio(channels_path)
    if verbose:
        print(
            f"[score] lib={len(lib)} target>={threshold}={len(target)} "
            f"channels={len(channel_prio)} threshold={threshold}",
            flush=True,
        )

    signals = _net_new_signals(conn, lib, target)

    # Universe = every successfully-fetched set, joined to its listing channel.
    rows = conn.execute(
        "SELECT sd.trackid_id AS tid, s.channel AS channel "
        "FROM set_detail sd JOIN trackid_index_staging s ON s.trackid_id=sd.trackid_id "
        "WHERE sd.http_status=200 ORDER BY sd.trackid_id"
    ).fetchall()

    per_phase = {0: 0, 1: 0, 2: 0, 3: 0}
    skipped = 0
    emitted = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for r in rows:
            tid = r["tid"]
            prio = channel_prio.get(r["channel"])
            has_lib, has_g10, net_new_count = signals.get(tid, (False, False, 0))
            phase = assign_phase(prio, has_lib, has_g10)
            if phase is None:
                skipped += 1
                continue
            bonus = net_new_bonus(net_new_count, bonus_cap, bonus_span)
            record = {
                "trackid_id": tid,
                "score": phase_scores[phase] + bonus,
                "score_components": {
                    "phase": phase,
                    "has_lib": bool(has_lib),
                    "has_g10": bool(has_g10),
                    "channel_prio": channel_prio_label(prio),
                    "net_new_count": net_new_count,
                },
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            per_phase[phase] += 1
            emitted += 1
    conn.close()

    if verbose:
        print(
            f"[score] emitted={emitted} skipped={skipped} "
            f"(phase0={per_phase[0]} phase1={per_phase[1]} "
            f"phase2={per_phase[2]} phase3={per_phase[3]}) -> {out_path}",
            flush=True,
        )
    return {"emitted": emitted, "skipped": skipped, "per_phase": per_phase}


# --- CLI ---------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default="data/staging.db")
    p.add_argument("--lib", default="data/lib_artists_nn.txt.gz")
    p.add_argument("--target", default="data/target_artists.txt.gz")
    p.add_argument("--channels", default="data/channels_prio.csv")
    p.add_argument("--out", default="data/trackid_scores.ndjson")
    p.add_argument(
        "--genre-threshold", type=int, default=default_genre_threshold(),
        help="min curated-genre track_count for has_g10 (env C12_GENRE_THRESHOLD)",
    )
    args = p.parse_args(argv)
    bonus_cap, bonus_span = load_bonus_params()
    score(
        args.db, args.lib, args.target, args.channels, args.out,
        args.genre_threshold, load_phase_scores(), bonus_cap, bonus_span,
    )


if __name__ == "__main__":
    sys.exit(main())
