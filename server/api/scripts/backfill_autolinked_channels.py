#!/usr/bin/env python
"""One-shot OPS catch-up: historical backfill of auto-linked YouTube channels (C14.b).

``autolink_official_channels`` first shipped without dispatching
``backfill_youtube_channel``, so the channels it created before that fix only see the
~15 uploads of their RSS feed. This script queues the missing backfill for each
channel whose ``signals.method`` is ``wikidata_deezer``.

It writes nothing to the database: ``--apply`` only queues Celery tasks. Re-running is
safe for the data (already-known videos are skipped) but spends YouTube quota again,
so run it ONCE. Each backfill spends about 1 unit per 50 videos listed + 1 per 50
durations read, capped at ``YOUTUBE_BACKFILL_MAX_VIDEOS`` per channel.

Convention: DRY-RUN by default (lists what WOULD be queued), ``--apply`` to queue,
``--stagger`` seconds between two backfills.

Usage (from the VPS):
    docker compose exec api python scripts/backfill_autolinked_channels.py          # dry-run
    docker compose exec api python scripts/backfill_autolinked_channels.py --apply
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # server/api -> models

from models import Channel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

AUTOLINK_METHOD = "wikidata_deezer"
DEFAULT_STAGGER_SECONDS = 60


def select_autolinked_channels(session):
    """Watched, non-excluded, resolved YouTube channels created by the auto-link.

    ``signals`` is filtered in Python to avoid a cross-dialect JSON query (the table
    holds a few hundred rows). Returns ``[(id, name), ...]`` ordered by id.
    """
    rows = session.execute(
        select(Channel.id, Channel.name, Channel.signals)
        .where(
            Channel.platform == "youtube",
            Channel.watched.is_(True),
            Channel.excluded.isnot(True),
            Channel.external_id.isnot(None),
        )
        .order_by(Channel.id.asc())
    ).all()
    return [
        (channel_id, name)
        for channel_id, name, signals in rows
        if (signals or {}).get("method") == AUTOLINK_METHOD
    ]


def queue_backfills(channels, send_task, *, stagger=DEFAULT_STAGGER_SECONDS):
    """Queue one staggered backfill per channel. Returns the number queued."""
    for index, (channel_id, _name) in enumerate(channels):
        send_task(
            "workers.tasks.backfill_youtube_channel",
            args=[channel_id],
            countdown=index * stagger,
        )
    return len(channels)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="queue the backfills")
    parser.add_argument("--stagger", type=int, default=DEFAULT_STAGGER_SECONDS)
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    with Session(engine) as session:
        channels = select_autolinked_channels(session)

    for channel_id, name in channels:
        print(f"  #{channel_id} {name}")
    print(f"{len(channels)} auto-linked channel(s)")

    if not args.apply:
        print("DRY-RUN: nothing queued (use --apply)")
        return

    from celery_client import celery

    queued = queue_backfills(channels, celery.send_task, stagger=args.stagger)
    print(f"{queued} backfill(s) queued, {args.stagger}s apart")


if __name__ == "__main__":
    main()
