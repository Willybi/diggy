"""Analytical reports (autonomous deliverables): completeness + volumetry.

Both read only the local staging + checkpoint — no network. They return plain
dicts (for the JSON artefact) and a rendered human-readable text block.
"""

from .mapping import dumps_compact


def completeness_report(store, total_known, deleted_in_rowcount=None):
    """Three-way reconciliation of the crawl's coverage.

    Compares:
      A. Σ(expected rowCount over planned windows)  — what the plan expected
      B. total_known                                — the platform rowCount (V6/prod)
      C. id-range span  max(id) - min(id) + 1       — a dense-id upper bound
      D. staging rows actually stored

    Interpretation hinges on the V5 answer (``deleted_in_rowcount``): if rowCount
    INCLUDES ``isDeleted`` rows, then A/B should match D closely; the id-range (C)
    is only an upper bound because TrackID ids are not perfectly dense (gaps from
    hard-deleted / never-listed ids), so C >= D is expected, not an anomaly.
    """
    lo, hi = store.id_bounds()
    id_span = (hi - lo + 1) if (lo is not None and hi is not None) else 0
    sum_expected = store.sum_expected()
    stored = store.staging_count()
    deleted = store.deleted_count()

    report = {
        "sum_expected_windows": sum_expected,  # A
        "total_known": total_known,            # B
        "id_range_span": id_span,              # C
        "id_min": lo,
        "id_max": hi,
        "staging_rows": stored,                # D
        "deleted_rows": deleted,
        "v5_deleted_in_rowcount": deleted_in_rowcount,
        "delta_stored_vs_known": stored - total_known if total_known else None,
        "delta_stored_vs_expected": stored - sum_expected,
        "window_states": store.window_state_counts(),
    }

    lines = [
        "== COMPLETENESS (3-way reconciliation) ==",
        f"A. Σ expected (plan windows) : {sum_expected}",
        f"B. total known (platform)    : {total_known}",
        f"C. id-range span (max-min+1) : {id_span}  [min={lo} max={hi}]",
        f"D. staging rows stored       : {stored}",
        f"   of which isDeleted        : {deleted}",
        f"   Δ stored vs known (D-B)   : {report['delta_stored_vs_known']}",
        f"   Δ stored vs expected (D-A): {report['delta_stored_vs_expected']}",
        f"   window states            : {report['window_states']}",
        "",
        _completeness_interpretation(report, deleted_in_rowcount),
    ]
    return report, "\n".join(lines)


def _completeness_interpretation(report, deleted_in_rowcount):
    if deleted_in_rowcount is None:
        v5 = (
            "V5 unresolved: run the probe to determine whether rowCount includes "
            "isDeleted rows before trusting A/B vs D."
        )
    elif deleted_in_rowcount:
        v5 = (
            "V5 = rowCount INCLUDES isDeleted rows -> A/B should match D closely; "
            "id-range C >= D is expected (id gaps, not loss)."
        )
    else:
        v5 = (
            "V5 = rowCount EXCLUDES isDeleted rows -> D may exceed A/B by the "
            "number of deleted rows surfaced in the listing."
        )
    return "Interpretation: " + v5


def volumetry_report(store, top_n=25, spike_min=200):
    """Distribution snapshot of the staging mirror."""
    with_styles, without_styles = store.styles_presence()
    report = {
        "staging_rows": store.staging_count(),
        "deleted_rows": store.deleted_count(),
        "status_distribution": store.status_distribution(),
        "top_channels": store.top_channels(top_n),
        "count_by_year_added": store.count_by_year("added_on"),
        "count_by_year_created": store.count_by_year("created_on"),
        "track_hit_rate_histogram": store.hitrate_histogram("track_hit_rate"),
        "time_hit_rate_histogram": store.hitrate_histogram("time_hit_rate"),
        "styles_presence": {"with": with_styles, "without": without_styles},
        "mass_import_spikes": store.mass_import_spikes(spike_min, limit=50),
    }

    lines = ["== VOLUMETRY ==", f"staging rows: {report['staging_rows']}"]
    lines.append(f"deleted rows: {report['deleted_rows']}")
    lines.append(f"status distribution: {report['status_distribution']}")
    lines.append(
        f"styles present: {with_styles} / absent: {without_styles}"
    )
    lines.append("")
    lines.append(f"top {top_n} channels:")
    for ch, n in report["top_channels"]:
        lines.append(f"  {n:>7}  {ch}")
    lines.append("")
    lines.append("count by year (addedOn):")
    for y, n in report["count_by_year_added"]:
        lines.append(f"  {y}: {n}")
    lines.append("")
    lines.append("track_hit_rate histogram (10 bins over [0,1]):")
    lines.append(f"  {report['track_hit_rate_histogram']}")
    lines.append("")
    lines.append(f"mass-import spikes (>= {spike_min} in one minute by one user):")
    for user, minute, n in report["mass_import_spikes"][:20]:
        lines.append(f"  {n:>6}  {minute}  by {user}")

    return report, "\n".join(lines)


def render_json(report):
    return dumps_compact(report)
