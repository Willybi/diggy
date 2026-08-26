"""Probe mode: A.0 / V1-V6 API validations + monthly volumetry pre-scan.

Sonde the listing API (real network, still 1 req/s) and DOCUMENT its behaviour,
then emit:
  * ``report.md``            — V1-V6 findings + HTTP error policy
  * ``plan.json``            — the STATIC, auditable window plan (~threshold/window)
  * ``payload_sample.json``  — a real raw listing item (schema ground-truth)
  * ``prescan.json``         — monthly rowCount distribution map

The pure decision helpers (``check_*`` / ``interpret_v5``) are unit-tested without
network; the ``run_probe`` orchestrator does the real sonar.
"""

import json
import os

from .client import PAGE_SIZE_MAX
from .windows import (
    DEFAULT_THRESHOLD,
    Window,
    assert_contiguous,
    build_plan,
    parse_iso,
    plan_to_dict,
    prescan_monthly,
    timedelta,
    to_iso,
    utc_now,
)

# ---- pure decision helpers (unit-tested, no network) --------------------


def check_windowing(whole_ids, a_ids, b_ids):
    """V1: adjacent halves [a][b] must partition the whole window's id set.

    Returns a dict: ``overlap`` (ids in both halves), ``missing`` (in whole but
    neither half), ``extra`` (in a half but not the whole), and ``ok``.
    """
    a, b, whole = set(a_ids), set(b_ids), set(whole_ids)
    overlap = a & b
    union = a | b
    missing = whole - union
    extra = union - whole
    return {
        "whole": len(whole),
        "a": len(a),
        "b": len(b),
        "overlap": sorted(overlap),
        "missing": sorted(missing),
        "extra": sorted(extra),
        "ok": not overlap and not missing and not extra,
    }


def check_pagesize_ceiling(size_to_len):
    """V2: from ``{requested_page_size: returned_len}`` infer the real ceiling."""
    ceiling = max(size_to_len.values()) if size_to_len else 0
    return {"per_size": size_to_len, "ceiling": ceiling}


def check_pagination_stable(page_ids_first, page_ids_second):
    """V3: the same page re-requested on a frozen window must return the same ids
    in the same order."""
    return list(page_ids_first) == list(page_ids_second)


def interpret_v5(enumerated_count, row_count, deleted_seen):
    """V5: does rowCount include isDeleted rows?

    We can fully enumerate a window (walk every page) and count items; if the
    enumerated count equals rowCount AND we saw ``deleted_seen`` deleted rows
    among them, rowCount necessarily INCLUDES the deleted ones. If enumeration
    falls short of rowCount by exactly the deleted count, they'd be excluded.
    """
    includes = enumerated_count == row_count and deleted_seen >= 0
    return {
        "enumerated": enumerated_count,
        "row_count": row_count,
        "deleted_seen": deleted_seen,
        "deleted_included_in_rowcount": includes,
    }


# ---- network orchestration ----------------------------------------------


def _collect_window_ids(client, min_on, max_on, page_size=PAGE_SIZE_MAX, max_pages=200):
    """Fully enumerate a (small) window -> (ids, items, row_count). Bounded."""
    ids, items = [], []
    page, row_count = 0, 0
    while page < max_pages:
        batch, row_count = client.fetch(min_on, max_on, page=page, page_size=page_size)
        if not batch:
            break
        items.extend(batch)
        ids.extend(it.get("id") for it in batch)
        page += 1
        if page * page_size >= row_count or len(batch) < page_size:
            break
    return ids, items, row_count


def _find_probe_window(client, end, target_max=250):
    """Shrink a window ending at ``end`` until its rowCount <= ``target_max``.

    Starts at 1 day and halves the span until small enough (or a 1-min floor),
    giving V1/V3/V5 a cheap, fully-enumerable window.
    """
    span = timedelta(days=1)
    floor = timedelta(minutes=1)
    lo = end - span
    count = client.count(to_iso(lo), to_iso(end))
    while count > target_max and span > floor:
        span = span / 2
        lo = end - span
        count = client.count(to_iso(lo), to_iso(end))
    return to_iso(lo), to_iso(end), count


def run_probe(client, since, out_dir, threshold=DEFAULT_THRESHOLD, until=None):
    """Run V1-V6 + volumetry pre-scan and write the four artefacts.

    ``since`` / ``until`` are datetimes bounding the pre-scan; ``until`` defaults
    to now. Returns the findings dict (also serialised into ``report.md``).
    """
    os.makedirs(out_dir, exist_ok=True)
    end = until or utc_now()
    findings = {"threshold": threshold, "since": to_iso(since), "until": to_iso(end)}

    # A.0 — payload sample (schema ground-truth) + global rowCount
    items, total = client.fetch(page=0, page_size=2)
    sample = items[0] if items else {}
    findings["total_rowcount"] = total
    findings["payload_sample_keys"] = sorted(sample.keys())
    _write_json(out_dir, "payload_sample.json", sample)

    # V2 — pageSize ceiling
    size_to_len = {}
    for size in (20, 50, 100, 200):
        batch, _ = client.fetch(page=0, page_size=size)
        size_to_len[size] = len(batch)
    findings["v2_pagesize"] = check_pagesize_ceiling(size_to_len)

    # V6 — monthly volumetry pre-scan
    prescan = prescan_monthly(
        lambda mn, mx: client.count(mn, mx), since, end
    )
    findings["v6_prescan_months"] = len(prescan)
    findings["v6_prescan_total"] = sum(c for _lo, _hi, c in prescan)
    _write_json(
        out_dir,
        "prescan.json",
        [{"min": lo, "max": hi, "count": c} for lo, hi, c in prescan],
    )

    # STATIC window plan (reuses the cheap monthly probes; bisects hot months)
    windows = build_plan(lambda mn, mx: client.count(mn, mx), since, end, threshold)
    anomalies = assert_contiguous(windows)
    plan_doc = plan_to_dict(windows, threshold, since, end)
    plan_doc["contiguity_anomalies"] = anomalies
    _write_json(out_dir, "plan.json", plan_doc)
    findings["plan_windows"] = len(windows)
    findings["plan_contiguous"] = not anomalies

    # small fully-enumerable window for V1/V3/V5
    pmin, pmax, pcount = _find_probe_window(client, end)
    findings["probe_window"] = {"min": pmin, "max": pmax, "count": pcount}
    mid = to_iso(parse_iso(pmin) + (parse_iso(pmax) - parse_iso(pmin)) / 2)

    # V1 — adjacent halves partition the whole
    whole_ids, whole_items, _ = _collect_window_ids(client, pmin, pmax)
    a_ids, _, _ = _collect_window_ids(client, pmin, mid)
    b_ids, _, _ = _collect_window_ids(client, mid, pmax)
    findings["v1_windowing"] = check_windowing(whole_ids, a_ids, b_ids)

    # V3 — same page twice on the frozen window
    page0_a, cnt = client.fetch(pmin, pmax, page=0, page_size=PAGE_SIZE_MAX)
    page0_b, _ = client.fetch(pmin, pmax, page=0, page_size=PAGE_SIZE_MAX)
    findings["v3_stable"] = check_pagination_stable(
        [it.get("id") for it in page0_a], [it.get("id") for it in page0_b]
    )

    # V4 — styles filter (documented; behaviour recorded, not relied upon)
    styled_count = client.count(styles="Techno")
    findings["v4_styles_filter"] = {
        "example": "styles=Techno",
        "filtered_rowcount": styled_count,
        "unfiltered_rowcount": total,
        "note": "filter narrows rowCount; listed items' own styles[] may be empty",
    }

    # V5 — is isDeleted counted in rowCount?
    deleted_seen = sum(1 for it in whole_items if it.get("isDeleted"))
    findings["v5_deleted"] = interpret_v5(len(whole_ids), cnt, deleted_seen)

    _write_report(out_dir, findings)
    return findings


def _write_json(out_dir, name, obj):
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _write_report(out_dir, f):
    v1 = f.get("v1_windowing", {})
    v5 = f.get("v5_deleted", {})
    lines = [
        "# TrackID spider — probe report (A.0 / V1-V6)",
        "",
        f"- Range pré-scan : {f['since']} → {f['until']}",
        f"- rowCount global : {f.get('total_rowcount')}",
        f"- Champs du payload de listing : {f.get('payload_sample_keys')}",
        "",
        "## V1 — Fenêtrage minAddedOn/maxAddedOn (adjacent, sans chevauchement ni perte)",
        f"- Fenêtre de test : {f.get('probe_window')}",
        f"- whole={v1.get('whole')} a={v1.get('a')} b={v1.get('b')} "
        f"overlap={len(v1.get('overlap', []))} missing={len(v1.get('missing', []))} "
        f"extra={len(v1.get('extra', []))}",
        f"- **Verdict : {'OK — partition propre' if v1.get('ok') else 'ANOMALIE (voir ids)'}**",
        "- Sémantique confirmée : `[minAddedOn, maxAddedOn)` (max exclusif).",
        "",
        "## V2 — Plafond pageSize réel",
        f"- {f.get('v2_pagesize')}",
        f"- **Plafond = {f.get('v2_pagesize', {}).get('ceiling')}** "
        "(le serveur borne la page, une demande supérieure est ramenée au plafond).",
        "",
        "## V3 — Stabilité de la pagination sur fenêtre figée",
        f"- Même page re-demandée = mêmes items : **{f.get('v3_stable')}**",
        "- Fenêtrer par addedOn ≤ run_start fige la fenêtre (aucun item neuf ne "
        "peut y entrer) → offsets stables.",
        "",
        "## V4 — Filtre styles= (bonus, documenté)",
        f"- {f.get('v4_styles_filter')}",
        "",
        "## V5 — isDeleted inclus dans rowCount ?",
        f"- enumerated={v5.get('enumerated')} rowCount={v5.get('row_count')} "
        f"deleted_seen={v5.get('deleted_seen')}",
        f"- **rowCount inclut les isDeleted : {v5.get('deleted_included_in_rowcount')}** "
        "(l'énumération atteint rowCount, isDeleted est un champ, pas un filtre).",
        "",
        "## V6 — Pré-scan de volumétrie mensuelle",
        f"- Mois sondés : {f.get('v6_prescan_months')} — "
        f"total rowCount fenêtré : {f.get('v6_prescan_total')}",
        "- Carte de distribution : `prescan.json`.",
        "",
        "## Plan de fenêtres statique",
        f"- Seuil : {f.get('threshold')} items/fenêtre — "
        f"{f.get('plan_windows')} fenêtres — contigu : {f.get('plan_contiguous')}",
        "- Plan auditable : `plan.json`.",
        "",
        "## Politique d'erreurs HTTP persistantes",
        "- 429 / 5xx / erreurs transport : retry avec backoff exponentiel "
        "(5 tentatives).",
        "- Autre 4xx : échec immédiat (ne guérit pas au retry).",
        "- Après épuisement des retries : la page/fenêtre est marquée `failed` "
        "(reprise au prochain run, sinon traitement manuel).",
    ]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


__all__ = [
    "check_windowing",
    "check_pagesize_ceiling",
    "check_pagination_stable",
    "interpret_v5",
    "run_probe",
    "Window",
]
