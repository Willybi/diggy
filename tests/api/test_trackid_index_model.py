"""Round-trip test for the TrackIdIndex model (C11 / L1).

Self-contained: builds its OWN in-memory SQLite engine and creates only the
trackid_index table, so it does not touch the PG fixtures/conftest harness.
Proves the model is SQLite-buildable (StringArray→JSON, JSON columns) and that
the array/json columns and the hydration_state default round-trip.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.trackid_index import TrackIdIndex


def test_trackid_index_round_trip():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    TrackIdIndex.__table__.create(engine)

    with Session(engine) as session:
        session.add(
            TrackIdIndex(
                trackid_id=42,
                title="Some Set",
                styles=["Techno", "House"],
                duration="01:23:45",
                status=3,
                audio_stream_type=1,
                raw_json={"id": 1, "foo": "bar"},
            )
        )
        session.commit()

    with Session(engine) as session:
        row = session.query(TrackIdIndex).filter_by(trackid_id=42).one()
        assert row.styles == ["Techno", "House"]
        assert row.raw_json == {"id": 1, "foo": "bar"}
        assert row.hydration_state == "not_hydrated"
        assert row.duration == "01:23:45"
        assert row.status == 3
        assert row.audio_stream_type == 1
