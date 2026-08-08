from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection


@contextmanager
def transaction(connection: Connection) -> Iterator[Connection]:
    try:
        with connection.transaction():
            yield connection
    except Exception:
        connection.rollback()
        raise
