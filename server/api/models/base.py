from sqlalchemy import JSON, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import TypeDecorator


class StringArray(TypeDecorator):
    """ARRAY(Text) on PostgreSQL, JSON on other dialects (e.g. SQLite for tests)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text))
        return dialect.type_descriptor(JSON)

    def process_bind_param(self, value, dialect):
        if value is None:
            return [] if dialect.name != "postgresql" else value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return []
        return list(value)
