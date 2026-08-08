from __future__ import annotations

from dotenv import dotenv_values
import psycopg


EXPECTED_TABLES = {
    "chat_audit",
    "decisions",
    "emails",
    "ingest_groups",
    "ingest_runs",
    "quality_feedback",
    "task_events",
    "threads",
}


def main() -> None:
    values = dotenv_values(".env")
    url = values.get("SUPABASE_MIGRATION_DB_URL") or values.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL is required")
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"

    with psycopg.connect(url, connect_timeout=10) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = %s",
                ("app_private",),
            ).fetchall()
        }
        indexes = connection.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = %s",
            ("app_private",),
        ).fetchall()
        rls = connection.execute(
            """
            SELECT relname, relrowsecurity
            FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = %s AND relkind = 'r'
            """,
            ("app_private",),
        ).fetchall()

    result = {
        "revision": revision[0] if revision else None,
        "tables": sorted(tables),
        "tables_match": tables == EXPECTED_TABLES,
        "index_count": len(indexes),
        "rls_table_count": len(rls),
        "all_rls_enabled": len(rls) == len(EXPECTED_TABLES) and all(row[1] for row in rls),
    }
    print(result)
    if not result["tables_match"] or not result["all_rls_enabled"]:
        raise SystemExit("Database verification failed")


if __name__ == "__main__":
    main()
