"""C11 — local TrackID.net listing spider (autonomous, no prod connection).

This package enumerates the public ``GET /api/public/audiostreams`` listing
exhaustively into a LOCAL SQLite staging mirror. It never touches prod, never
imports the ``server`` package, and writes only to a local SQLite file. A later
lot (L3) imports the exported staging into the prod ``trackid_index`` table.

Modules:
  mapping  — raw camelCase listing item -> snake_case column contract (+ raw_json)
  client   — sync, strictly rate-limited (1 req/s) HTTP client with backoff
  store    — SQLite staging mirror + per-window crawl checkpoint + export
  windows  — static window plan model + adaptive time-window builder
  probe    — probe mode (A.0 / V1-V6 validations + monthly volumetry prescan)
  crawl    — crawl mode (consume plan, resume idempotently, upsert)
  reports  — completeness (3-way reconciliation) + volumetry reports
  spider   — argparse CLI entrypoint
"""
