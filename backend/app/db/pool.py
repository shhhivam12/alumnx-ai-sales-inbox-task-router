from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.app.config import Settings


class DatabasePool:
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_db_url:
            raise ValueError("SUPABASE_DB_URL is not configured")
        self.pool = ConnectionPool(
            conninfo=settings.supabase_db_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            max_lifetime=settings.db_pool_recycle_seconds,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=False,
            check=ConnectionPool.check_connection,
        )

    def open(self) -> None:
        self.pool.open(wait=True)

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with self.pool.connection() as connection:
            yield connection

    def health(self) -> bool:
        try:
            with self.connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() is not None
        except Exception:
            return False

    def migration_ready(self) -> bool:
        try:
            with self.connection() as connection, connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version WHERE version_num = '0002_local_task_api'")
                return cursor.fetchone() is not None
        except Exception:
            return False
