#!/usr/bin/env python
"""C11 — local TrackID.net listing spider CLI (autonomous, no prod connection).

Enumerates the public ``GET /api/public/audiostreams`` listing exhaustively into
a LOCAL SQLite staging mirror, at a STRICT 1 req/s. A later lot (L3) imports the
exported staging into the prod ``trackid_index`` table.

Subcommands:
  probe   — sonde the API (A.0 / V1-V6) + monthly volumetry pre-scan; write
            report.md + plan.json + payload_sample.json + prescan.json
  crawl   — consume plan.json, crawl every window into staging.db (idempotent,
            resumable, final pass over [run_start, now))
  export  — dump staging.db to CSV or NDJSON in the exact column contract
  report  — write the completeness (3-way) + volumetry reports from staging.db
  status  — print the crawl window-state summary

Usage (from the repo root):
  python scripts/local/trackid_spider/spider.py probe  --since 2016-01
  python scripts/local/trackid_spider/spider.py crawl
  python scripts/local/trackid_spider/spider.py export --format csv
  python scripts/local/trackid_spider/spider.py report --total-known 381486
"""

import argparse
import csv
import functools
import json
import os
import sys

# Support both ``python -m scripts.local.trackid_spider.spider`` (package import)
# and ``python scripts/local/trackid_spider/spider.py`` (script path).
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))))
    from scripts.local.trackid_spider import client as client_mod
    from scripts.local.trackid_spider import crawl as crawl_mod
    from scripts.local.trackid_spider import probe as probe_mod
    from scripts.local.trackid_spider import reports as reports_mod
    from scripts.local.trackid_spider.logs import JsonLogger
    from scripts.local.trackid_spider.mapping import COLUMNS
    from scripts.local.trackid_spider.store import Store, row_to_export_values
    from scripts.local.trackid_spider.windows import (
        DEFAULT_THRESHOLD,
        parse_iso,
        plan_from_dict,
    )
else:  # pragma: no cover - exercised via import in tests
    from . import client as client_mod
    from . import crawl as crawl_mod
    from . import probe as probe_mod
    from . import reports as reports_mod
    from .logs import JsonLogger
    from .mapping import COLUMNS
    from .store import Store, row_to_export_values
    from .windows import DEFAULT_THRESHOLD, parse_iso, plan_from_dict

print = functools.partial(print, flush=True)  # noqa: A001

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_WORKDIR = os.path.join(PKG_DIR, "data")


def _parse_since(value):
    """Accept ``YYYY``, ``YYYY-MM`` or a full ISO timestamp -> aware UTC datetime."""
    v = value.strip()
    if len(v) == 4 and v.isdigit():
        v = f"{v}-01-01T00:00:00Z"
    elif len(v) == 7:  # YYYY-MM
        v = f"{v}-01T00:00:00Z"
    elif "T" not in v:  # YYYY-MM-DD
        v = f"{v}T00:00:00Z"
    return parse_iso(v)


def cmd_probe(args):
    since = _parse_since(args.since)
    out_dir = os.path.abspath(args.workdir)
    with client_mod.ListingClient() as client:
        findings = probe_mod.run_probe(
            client, since, out_dir, threshold=args.threshold
        )
    print(f"[probe] wrote report.md / plan.json / payload_sample.json / prescan.json "
          f"to {out_dir}")
    print(f"[probe] {findings['plan_windows']} planned window(s); "
          f"pageSize ceiling={findings['v2_pagesize']['ceiling']}; "
          f"V1 ok={findings['v1_windowing']['ok']}; V3 stable={findings['v3_stable']}; "
          f"V5 deleted_in_rowcount={findings['v5_deleted']['deleted_included_in_rowcount']}")


def cmd_crawl(args):
    out_dir = os.path.abspath(args.workdir)
    plan_path = args.plan or os.path.join(out_dir, "plan.json")
    if not os.path.exists(plan_path):
        sys.exit(f"crawl: no plan at {plan_path} — run `probe` first")
    with open(plan_path, encoding="utf-8") as f:
        plan = plan_from_dict(json.load(f))

    db_path = os.path.join(out_dir, args.db)
    log_path = os.path.join(out_dir, "crawl.log.jsonl")
    logger = JsonLogger(log_path)
    with Store(db_path) as store, client_mod.ListingClient() as client:
        summary = crawl_mod.run_crawl(
            store, client, plan, logger,
            page_size=args.page_size, final_pass=not args.no_final_pass,
        )
    logger.close()
    print(f"[crawl] done — {summary['staging_rows']} staging rows; "
          f"window states={summary['states']}")


def cmd_export(args):
    out_dir = os.path.abspath(args.workdir)
    db_path = os.path.join(out_dir, args.db)
    if not os.path.exists(db_path):
        sys.exit(f"export: no staging db at {db_path}")
    out_path = args.out or os.path.join(
        out_dir, f"trackid_index.{ 'ndjson' if args.format == 'ndjson' else 'csv'}"
    )
    with Store(db_path) as store:
        n = _export(store, out_path, args.format)
    print(f"[export] {n} row(s) -> {out_path} ({args.format}, column contract)")


def _export(store, out_path, fmt):
    n = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        if fmt == "ndjson":
            for row in store.iter_export_rows():
                # keys already in contract order (dict built from COLUMNS)
                f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
                f.write("\n")
                n += 1
        else:
            writer = csv.writer(f)
            writer.writerow(COLUMNS)
            for row in store.iter_export_rows():
                writer.writerow(row_to_export_values(row))
                n += 1
    return n


def cmd_report(args):
    out_dir = os.path.abspath(args.workdir)
    db_path = os.path.join(out_dir, args.db)
    if not os.path.exists(db_path):
        sys.exit(f"report: no staging db at {db_path}")
    with Store(db_path) as store:
        comp, comp_txt = reports_mod.completeness_report(
            store, args.total_known, args.v5_deleted_in_rowcount
        )
        vol, vol_txt = reports_mod.volumetry_report(store)
    _write(os.path.join(out_dir, "report_completeness.json"), reports_mod.render_json(comp))
    _write(os.path.join(out_dir, "report_volumetry.json"), reports_mod.render_json(vol))
    _write(os.path.join(out_dir, "report_completeness.txt"), comp_txt)
    _write(os.path.join(out_dir, "report_volumetry.txt"), vol_txt)
    print(comp_txt)
    print()
    print(vol_txt)


def cmd_status(args):
    out_dir = os.path.abspath(args.workdir)
    db_path = os.path.join(out_dir, args.db)
    if not os.path.exists(db_path):
        sys.exit(f"status: no staging db at {db_path}")
    with Store(db_path) as store:
        states = store.window_state_counts()
        rows = store.staging_count()
        lo, hi = store.id_bounds()
        run_start = store.get_meta("run_start")
    print(f"run_start={run_start}  staging_rows={rows}  id=[{lo}..{hi}]")
    print(f"window states: {states}")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def build_parser():
    p = argparse.ArgumentParser(
        description="Local TrackID.net listing spider (C11, autonomous, no prod)"
    )
    p.add_argument(
        "--workdir", default=DEFAULT_WORKDIR,
        help="working dir for staging.db + plan.json + reports (default: <pkg>/data)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("probe", help="A.0/V1-V6 validations + volumetry pre-scan + plan")
    sp.add_argument("--since", default="2016-01",
                    help="pre-scan start (YYYY | YYYY-MM | ISO), default 2016-01")
    sp.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                    help=f"max items/window in the plan (default {DEFAULT_THRESHOLD})")
    sp.set_defaults(func=cmd_probe)

    sc = sub.add_parser("crawl", help="crawl the plan into staging (idempotent, resumable)")
    sc.add_argument("--plan", help="plan.json path (default: <workdir>/plan.json)")
    sc.add_argument("--db", default="staging.db", help="staging db filename")
    sc.add_argument("--page-size", type=int, default=client_mod.PAGE_SIZE_MAX,
                    help=f"page size (server caps at {client_mod.PAGE_SIZE_MAX})")
    sc.add_argument("--no-final-pass", action="store_true",
                    help="skip the [run_start, now) mop-up pass")
    sc.set_defaults(func=cmd_crawl)

    se = sub.add_parser("export", help="export staging to CSV/NDJSON (column contract)")
    se.add_argument("--db", default="staging.db", help="staging db filename")
    se.add_argument("--format", choices=("csv", "ndjson"), default="csv")
    se.add_argument("--out", help="output path (default: <workdir>/trackid_index.<ext>)")
    se.set_defaults(func=cmd_export)

    sr = sub.add_parser("report", help="completeness (3-way) + volumetry reports")
    sr.add_argument("--db", default="staging.db", help="staging db filename")
    sr.add_argument("--total-known", type=int, default=0,
                    help="platform rowCount for the 3-way reconciliation (V6/prod)")
    sr.add_argument("--v5-deleted-in-rowcount", type=_optbool, default=None,
                    help="V5 answer (true/false) to interpret the reconciliation")
    sr.set_defaults(func=cmd_report)

    ss = sub.add_parser("status", help="print the crawl window-state summary")
    ss.add_argument("--db", default="staging.db", help="staging db filename")
    ss.set_defaults(func=cmd_status)
    return p


def _optbool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "y", "t")


def _force_utf8_stdout():
    """The console glyphs (Σ, →, ✓, ✗) crash on a Windows cp1252 stdout — this is
    a Windows-run tool, so make stdout/stderr UTF-8 (errors=replace) defensively."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None):
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
