"""Round-trip test for the Channel model (C14.b / L1).

Self-contained: builds its OWN in-memory SQLite engine and creates only the
channels table, so it does not touch the PG fixtures/conftest harness (xdist
safe). Proves the model is SQLite-buildable (partial index carries sqlite_where,
JSON column) and that the boolean defaults + a minimal row round-trip.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.channel import Channel


def test_channel_round_trip():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Channel.__table__.create(engine)

    with Session(engine) as session:
        session.add(
            Channel(
                platform="youtube",
                external_id="UC1234567890",
                name="Boiler Room",
                channel_type="organizer",
                watched=True,
                signals={"subs": 1000},
            )
        )
        session.commit()

    with Session(engine) as session:
        row = session.query(Channel).filter_by(external_id="UC1234567890").one()
        assert row.platform == "youtube"
        assert row.name == "Boiler Room"
        assert row.channel_type == "organizer"
        assert row.watched is True
        # server_default="false" applies to an unset boolean
        assert row.excluded is False
        assert row.signals == {"subs": 1000}
        assert row.artist_id is None


def test_channel_minimal_row_defaults():
    """A minimal row (only the NOT NULL cols) gets its boolean server_defaults."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Channel.__table__.create(engine)

    with Session(engine) as session:
        session.add(Channel(platform="youtube", name="Some Artist"))
        session.commit()

    with Session(engine) as session:
        row = session.query(Channel).one()
        assert row.external_id is None
        assert row.channel_type is None
        assert row.watched is False
        assert row.excluded is False
