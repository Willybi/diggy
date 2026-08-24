from sqlalchemy import JSON, Boolean, Float, Text, literal
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


class array_is_empty(FunctionElement):
    """True when a :class:`StringArray` column is empty or NULL.

    Compiled per dialect so the same ORM expression runs on PostgreSQL
    (``TEXT[]``) and on SQLite, where :class:`StringArray` is stored as JSON
    (test harness). Mirrors the empty-genres predicate of
    ``genres_unclassified_count`` (``coalesce(array_length(col, 1), 0) = 0``).
    """

    type = Boolean()
    name = "array_is_empty"
    inherit_cache = True


@compiles(array_is_empty)
def _array_is_empty_default(element, compiler, **kw):
    (col,) = list(element.clauses)
    return f"coalesce(array_length({compiler.process(col, **kw)}, 1), 0) = 0"


@compiles(array_is_empty, "sqlite")
def _array_is_empty_sqlite(element, compiler, **kw):
    (col,) = list(element.clauses)
    return f"coalesce(json_array_length({compiler.process(col, **kw)}), 0) = 0"


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


class EmbeddingVector(TypeDecorator):
    """A fixed-dimension float vector: ``pgvector`` ``Vector(dim)`` on PostgreSQL,
    JSON (a list of floats) on other dialects (e.g. SQLite for tests).

    Same spirit as :class:`StringArray` — the ORM column round-trips a plain
    Python ``list[float]`` on both dialects, so application code never sees the
    dialect difference. ``pgvector`` is imported lazily inside the PostgreSQL
    branch so the SQLite test path has no hard dependency on it.
    """

    impl = JSON
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):
        def cosine_distance(self, other):
            """pgvector cosine distance (``<=>``) — PostgreSQL only.

            Same spirit as :class:`StringArray`'s explicit comparator: a bare
            ``TypeDecorator`` does NOT inherit pgvector's distance ops, so we
            expose the one operator the content-neighbour query (C9.b) needs.
            Only ever compiled on PostgreSQL (the KNN query runs there); the
            SQLite test path — which stores the column as JSON and has no
            vector ops — never reaches this branch.
            """
            return self.op("<=>", return_type=Float())(other)

    def __init__(self, dim, *args, **kwargs):
        self.dim = dim
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return list(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [float(x) for x in value]
