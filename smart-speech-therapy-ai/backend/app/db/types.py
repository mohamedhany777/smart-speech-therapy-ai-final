"""
Custom column types that behave correctly on both PostgreSQL (production)
and SQLite (local dev / tests) without needing extra extensions.
"""
import uuid

from sqlalchemy.types import CHAR, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID type when available, otherwise stores as a
    32-char hex string (no dashes) on SQLite / other backends.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    # A well-formed UUID that no real row will ever have. Used when a lookup is
    # attempted with a malformed identifier (e.g. GET /games/abc/start) so the
    # query simply matches nothing and the endpoint's normal 404 path runs,
    # instead of the driver raising and the API answering 500.
    _NO_MATCH = uuid.UUID(int=0)

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            try:
                value = uuid.UUID(str(value))
            except (ValueError, AttributeError, TypeError):
                value = self._NO_MATCH
        if dialect.name == "postgresql":
            return str(value)
        return value.hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(value)
