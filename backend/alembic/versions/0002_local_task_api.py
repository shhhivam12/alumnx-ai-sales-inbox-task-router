"""Add the persistent grader-facing Task API table.

Revision ID: 0002_local_task_api
Revises: 0001_initial
"""

from alembic import op


revision = "0002_local_task_api"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE app_private.tasks (
        task_id TEXT PRIMARY KEY,
        candidate_id TEXT NOT NULL,
        source_email_id TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
        description TEXT NULL CHECK (description IS NULL OR char_length(description) <= 2000),
        assignee_id TEXT NOT NULL CHECK (assignee_id IN ('u_aarti','u_rohit','u_meera','u_karan','u_divya','u_triage')),
        category TEXT NOT NULL CHECK (category IN ('enterprise_rfp','smb_enquiry','marketing','alliances','finance','triage')),
        priority TEXT NOT NULL CHECK (priority IN ('high','medium','low')),
        due_date DATE NULL,
        deal_value_inr BIGINT NULL CHECK (deal_value_inr IS NULL OR deal_value_inr >= 0),
        company_name TEXT NULL CHECK (company_name IS NULL OR char_length(company_name) <= 256),
        confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    CREATE INDEX tasks_candidate_thread_idx ON app_private.tasks(candidate_id, thread_id);
    CREATE INDEX tasks_candidate_source_idx ON app_private.tasks(candidate_id, source_email_id);
    CREATE INDEX tasks_candidate_assignee_idx ON app_private.tasks(candidate_id, assignee_id);
    CREATE INDEX tasks_candidate_category_idx ON app_private.tasks(candidate_id, category);
    ALTER TABLE app_private.tasks ENABLE ROW LEVEL SECURITY;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_private.tasks;")
