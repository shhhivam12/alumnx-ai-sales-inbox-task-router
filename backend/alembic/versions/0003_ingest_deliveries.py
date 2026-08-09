"""Track every delivered email without duplicating its immutable decision.

Revision ID: 0003_ingest_deliveries
Revises: 0002_local_task_api
"""

from alembic import op


revision = "0003_ingest_deliveries"
down_revision = "0002_local_task_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE app_private.ingest_deliveries (
        id UUID PRIMARY KEY,
        run_id UUID NOT NULL REFERENCES app_private.ingest_runs(id) ON DELETE CASCADE,
        candidate_id TEXT NOT NULL,
        email_id TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('create','update','skip','noop','unchanged')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (candidate_id, run_id, email_id)
    );
    CREATE INDEX deliveries_run_idx
        ON app_private.ingest_deliveries(candidate_id, run_id, created_at);
    CREATE INDEX deliveries_email_idx
        ON app_private.ingest_deliveries(candidate_id, email_id, created_at);
    ALTER TABLE app_private.ingest_deliveries ENABLE ROW LEVEL SECURITY;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_private.ingest_deliveries;")
