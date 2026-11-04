"""Tests for the OPS catch-up script scripts/backfill_autolinked_channels.

Exercises the selection against a real sync SQLite session (``sync_session``
fixture) and the queueing with an injected ``send_task``. Same import/path pattern
as test_backfill_set_reliability.py.
"""
import os
import sys
from unittest.mock import MagicMock

_SERVER_API = os.path.join(os.path.dirname(__file__), "../../server/api")
if _SERVER_API not in sys.path:
    sys.path.insert(0, _SERVER_API)

from models import Channel  # noqa: E402
from scripts.backfill_autolinked_channels import (  # noqa: E402
    queue_backfills,
    select_autolinked_channels,
)

_AUTO = {"method": "wikidata_deezer", "confidence": "high"}


def _add(session, external_id, *, name="C", signals=_AUTO, **fields):
    row = Channel(
        platform=fields.pop("platform", "youtube"),
        external_id=external_id,
        name=name,
        watched=fields.pop("watched", True),
        excluded=fields.pop("excluded", False),
        signals=signals,
    )
    session.add(row)
    session.flush()
    return row.id


def test_selects_only_active_autolinked_channels(sync_session):
    kept = _add(sync_session, "UC1", name="Auto")
    _add(sync_session, "UC2", signals=None)  # added by hand
    _add(sync_session, "UC3", signals={"method": "search"})
    _add(sync_session, "UC4", watched=False)
    _add(sync_session, "UC5", excluded=True)
    _add(sync_session, None, signals={"method": "wikidata_deezer"})  # unresolved
    _add(sync_session, "SC1", platform="soundcloud")

    assert select_autolinked_channels(sync_session) == [(kept, "Auto")]


def test_queue_backfills_staggers_each_channel():
    send_task = MagicMock()

    queued = queue_backfills([(7, "A"), (9, "B")], send_task, stagger=60)

    assert queued == 2
    calls = send_task.call_args_list
    assert [c.args[0] for c in calls] == ["workers.tasks.backfill_youtube_channel"] * 2
    assert [c.kwargs["args"] for c in calls] == [[7], [9]]
    assert [c.kwargs["countdown"] for c in calls] == [0, 60]


def test_queue_backfills_with_nothing_to_do():
    send_task = MagicMock()

    assert queue_backfills([], send_task) == 0
    send_task.assert_not_called()
