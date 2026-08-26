"""Crawl mode: consume the static window plan, upsert into staging, resume safely.

Guarantees:
  * STRICT 1 req/s, no parallelism (enforced by the ListingClient throttle).
  * IDEMPOTENT resume — ``pages_done`` is persisted after each imported page, so
    an interruption resumes mid-window; the staging upsert (PK trackid_id) makes
    any re-fetch (resume, boundary overlap, final pass) lossless.
  * OVERFLOW detection — a window whose observed rowCount at run time exceeds its
    planned ``expected_count`` is flagged ``overflow`` (the plan under-counted;
    the extra pages are still crawled, so no data is lost — it's a signal).
  * FINAL PASS — after every planned window, ``[run_start, now)`` captures any
    item added while the crawl was running.
  * A persistent HTTP error (after the client's retries) marks the window
    ``failed`` and moves on — failed windows are listed for manual handling and
    retried on the next run.
"""

from .client import PAGE_SIZE_MAX, PersistentHTTPError
from .mapping import map_item
from .windows import final_pass_window, to_iso, utc_now


def _window_counters(rows):
    """Per-window rollup: items, deleted, status distribution, styles presence."""
    counters = {
        "items": len(rows),
        "deleted": 0,
        "with_styles": 0,
        "status": {},
    }
    for r in rows:
        if r["is_deleted"]:
            counters["deleted"] += 1
        if r["styles"] not in ("[]", "", None):
            counters["with_styles"] += 1
        st = r["status"]
        counters["status"][st] = counters["status"].get(st, 0) + 1
    return counters


def crawl_window(store, client, window_row, logger, page_size=PAGE_SIZE_MAX):
    """Crawl a single window to exhaustion, resuming from its ``pages_done``.

    ``window_row`` is a sqlite Row from ``crawl_windows``. Returns the aggregated
    per-window counters dict (also emitted as a structured log event).
    """
    window_id = window_row["window_id"]
    min_on = window_row["min_added_on"]
    max_on = window_row["max_added_on"]
    expected = window_row["expected_count"]

    page = window_row["pages_done"] or 0
    store.update_window(window_id, utc_now_iso(), state="in_progress")
    logger.event(
        "window_start",
        human=f"→ window {window_id} [{min_on} .. {max_on}) "
        f"expected={expected} resume_page={page}",
        window_id=window_id,
        min_added_on=min_on,
        max_added_on=max_on,
        expected=expected,
        resume_page=page,
    )

    agg = {"items": 0, "deleted": 0, "with_styles": 0, "status": {}}
    observed = None
    try:
        while True:
            items, row_count = client.fetch(min_on, max_on, page=page, page_size=page_size)
            observed = row_count
            if not items:
                break
            rows = [map_item(it, window_id) for it in items]
            store.upsert_items(rows, utc_now_iso())
            page += 1
            store.update_window(
                window_id,
                utc_now_iso(),
                pages_done=page,
                observed_count=observed,
                state="in_progress",
            )
            c = _window_counters(rows)
            _merge_counters(agg, c)
            logger.event(
                "page",
                window_id=window_id,
                page=page,
                page_items=len(items),
                row_count=row_count,
            )
            # Done when we've paged past the (windowed) total, or the API returned
            # a short page (last page). Both guard against an infinite loop.
            if page * page_size >= row_count or len(items) < page_size:
                break

        overflow = (
            expected is not None
            and observed is not None
            and observed > expected
        )
        store.update_window(
            window_id,
            utc_now_iso(),
            state="overflow" if overflow else "done",
            observed_count=observed,
            overflow=1 if overflow else 0,
        )
        logger.event(
            "window_done",
            human=f"✓ window {window_id}: {agg['items']} items "
            f"(observed={observed}, expected={expected}"
            f"{', OVERFLOW' if overflow else ''})",
            window_id=window_id,
            observed=observed,
            expected=expected,
            overflow=overflow,
            **agg,
        )
        return agg
    except PersistentHTTPError as exc:
        store.update_window(
            window_id, utc_now_iso(), state="failed", error=str(exc)
        )
        logger.event(
            "window_failed",
            human=f"✗ window {window_id} FAILED: {exc}",
            window_id=window_id,
            error=str(exc),
        )
        return agg


def _merge_counters(agg, c):
    agg["items"] += c["items"]
    agg["deleted"] += c["deleted"]
    agg["with_styles"] += c["with_styles"]
    for st, n in c["status"].items():
        agg["status"][st] = agg["status"].get(st, 0) + n


def utc_now_iso():
    return to_iso(utc_now())


def run_crawl(store, client, plan, logger, page_size=PAGE_SIZE_MAX, final_pass=True):
    """Load the plan, crawl every active window, then the final pass.

    ``run_start`` is stamped once (first run) and reused on resume so the final
    pass covers the entire crawl duration even across restarts.
    """
    run_start = store.get_meta("run_start")
    if not run_start:
        run_start = utc_now_iso()
        store.set_meta("run_start", run_start)
    store.set_meta("total_known", plan_total(plan))

    store.load_plan(plan, utc_now_iso())
    # Retry windows that FAILED in a previous run (between-run retry): flip them
    # back to pending, preserving pages_done. A window that fails THIS run stays
    # failed (not re-selected below) and is retried on the NEXT run.
    store.reset_failed_windows(utc_now_iso())
    logger.event(
        "crawl_start",
        human=f"crawl start — {len(plan)} planned window(s), run_start={run_start}",
        planned_windows=len(plan),
        run_start=run_start,
    )

    total_expected = store.sum_expected()
    done_items = 0
    import_time = _mono()
    while True:
        # Only pending/in_progress (never failed) — a window that fails this run
        # is not re-picked, so the loop always terminates.
        to_crawl = store.windows_to_crawl()
        if not to_crawl:
            break
        window_row = to_crawl[0]
        agg = crawl_window(store, client, window_row, logger, page_size)
        done_items += agg["items"]
        _emit_progress(logger, store, done_items, total_expected, import_time)

    failed = [w for w in store.active_windows() if w["state"] == "failed"]

    if final_pass:
        fw = final_pass_window(run_start)
        store.load_plan([fw], utc_now_iso())
        window_row = store.get_window(fw.window_id)
        logger.event("final_pass_start", human=f"final pass {fw.window_id}")
        crawl_window(store, client, window_row, logger, page_size)

    state_counts = store.window_state_counts()
    logger.event(
        "crawl_end",
        human=f"crawl end — staging rows={store.staging_count()}, "
        f"windows={state_counts}, failed={len(failed)}",
        staging_rows=store.staging_count(),
        window_states=state_counts,
        failed_windows=[w["window_id"] for w in failed],
    )
    return {"staging_rows": store.staging_count(), "states": state_counts}


def _emit_progress(logger, store, done_items, total_expected, start_mono):
    from .logs import format_eta

    elapsed = _mono() - start_mono
    logger.event(
        "progress",
        human=f"  progress: {done_items}/{total_expected} items "
        f"(~{format_eta(done_items, total_expected, elapsed)} ETA)",
        done_items=done_items,
        total_expected=total_expected,
        elapsed_s=round(elapsed, 1),
    )


def plan_total(plan):
    return sum(w.expected_count or 0 for w in plan)


def _mono():
    import time

    return time.monotonic()
