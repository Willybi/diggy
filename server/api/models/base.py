from sqlalchemy import JSON, Boolean, Text, literal
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement
from sqlalchemy.types import TypeDecorator


class array_any(FunctionElement):
    """Membership test on a :class:`StringArray` column: ``value = ANY (col)``.

    Compiled per dialect so the same ORM expression runs on PostgreSQL
    (``TEXT[]``) and on SQLite, where :class:`StringArray` is stored as JSON
    (test harness) — there it becomes a correlated ``json_each`` EXISTS.
    """

    type = Boolean()
    name = "array_any"
    inherit_cache = True


@compiles(array_any)
def _array_any_default(element, compiler, **kw):
    col, value = list(element.clauses)
    return f"{compiler.process(value, **kw)} = ANY ({compiler.process(col, **kw)})"


@compiles(array_any, "sqlite")
def _array_any_sqlite(element, compiler, **kw):
    col, value = list(element.clauses)
    return (
        f"EXISTS (SELECT 1 FROM json_each({compiler.process(col, **kw)}) "
        f"WHERE json_each.value = {compiler.process(value, **kw)})"
    )


class StringArray(TypeDecorator):
    """ARRAY(Text) on PostgreSQL, JSON on other dialects (e.g. SQLite for tests)."""

    impl = Text
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):
        def any(self, other, **kw):
            """Cross-DB ``other IN array`` predicate (see :class:`array_any`)."""
            return array_any(self.expr, literal(other, type_=Text()))

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
