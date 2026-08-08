"""Create the private operational schema.

Revision ID: 0001_initial
Revises: None
"""
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


DDL = r"""
CREATE SCHEMA IF NOT EXISTS app_private;
REVOKE ALL ON SCHEMA app_private FROM PUBLIC, anon, authenticated;

CREATE TABLE app_private.ingest_groups (
    id UUID PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    client_batch_id UUID NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('pasted','uploaded','generated','grader','api')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, client_batch_id)
);

CREATE TABLE app_private.ingest_runs (
    id UUID PRIMARY KEY,
    group_id UUID NULL REFERENCES app_private.ingest_groups(id),
    candidate_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing','completed','failed')),
    received_count INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    tasks_created INTEGER NOT NULL DEFAULT 0,
    tasks_updated INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE app_private.emails (
    id UUID PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    message_index INTEGER NOT NULL CHECK (message_index >= 0),
    raw_email JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    normalized_body TEXT NOT NULL,
    latest_reply_body TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    first_seen_run_id UUID NOT NULL REFERENCES app_private.ingest_runs(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, email_id),
    UNIQUE (candidate_id, thread_id, message_index)
);

CREATE TABLE app_private.decisions (
    id UUID PRIMARY KEY,
    email_row_id UUID UNIQUE NOT NULL REFERENCES app_private.emails(id),
    candidate_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('create','update','skip','noop')),
    decision_status TEXT NOT NULL CHECK (decision_status IN ('classified','reconciled','failed')),
    actionability TEXT NOT NULL CHECK (actionability IN ('actionable','non_actionable','ambiguous')),
    skip_reason TEXT NULL CHECK (skip_reason IN ('out_of_office','newsletter','vendor_spam','automated_bounce')),
    assignee_id TEXT NULL CHECK (assignee_id IN ('u_aarti','u_rohit','u_meera','u_karan','u_divya','u_triage')),
    category TEXT NULL CHECK (category IN ('enterprise_rfp','smb_enquiry','marketing','alliances','finance','triage')),
    priority TEXT NULL CHECK (priority IN ('high','medium','low')),
    deadline_at TIMESTAMPTZ NULL,
    due_date DATE NULL,
    deal_value_inr BIGINT NULL CHECK (deal_value_inr >= 0),
    company_name TEXT NULL,
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    primary_intents JSONB NOT NULL DEFAULT '[]'::jsonb,
    topics TEXT[] NOT NULL DEFAULT '{}',
    intent_direction TEXT NOT NULL,
    organization_type TEXT NOT NULL,
    alliance_subtype TEXT NULL,
    marketing_subtype TEXT NULL,
    amount_mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
    deadline_mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasoning TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    degraded_mode BOOLEAN NOT NULL DEFAULT false,
    model_name TEXT NULL,
    prompt_version TEXT NOT NULL,
    remote_task_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, email_id)
);

CREATE TABLE app_private.threads (
    id UUID PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    remote_task_id TEXT NULL,
    source_email_id TEXT NULL,
    current_task_snapshot JSONB NULL,
    last_message_index INTEGER NOT NULL DEFAULT -1,
    message_count INTEGER NOT NULL DEFAULT 0,
    update_count INTEGER NOT NULL DEFAULT 0,
    reconciliation_status TEXT NOT NULL DEFAULT 'empty' CHECK (reconciliation_status IN ('empty','mapped','conflict','error')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, thread_id)
);

CREATE TABLE app_private.task_events (
    id UUID PRIMARY KEY,
    operation_key TEXT UNIQUE NOT NULL,
    candidate_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    remote_task_id TEXT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('create','update','adopt','noop')),
    status TEXT NOT NULL CHECK (status IN ('pending','confirmed','failed')),
    before_snapshot JSONB NULL,
    patch JSONB NULL,
    after_snapshot JSONB NULL,
    external_status INTEGER NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ NULL
);

CREATE TABLE app_private.quality_feedback (
    id UUID PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    label TEXT NOT NULL CHECK (label IN ('correct','misrouted','missed','spurious')),
    note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (candidate_id, email_id)
);

CREATE TABLE app_private.chat_audit (
    id UUID PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('run','batch','all')),
    scope_id TEXT NULL,
    question TEXT NOT NULL,
    validated_plan JSONB NOT NULL,
    supporting_data JSONB NOT NULL,
    answer TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('answered','refused','unsupported','fallback','error')),
    model_name TEXT NULL,
    prompt_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX decisions_category_idx ON app_private.decisions(candidate_id, category);
CREATE INDEX decisions_priority_confidence_idx ON app_private.decisions(candidate_id, priority, confidence);
CREATE INDEX decisions_skip_idx ON app_private.decisions(candidate_id, skip_reason);
CREATE INDEX decisions_topics_idx ON app_private.decisions USING GIN(topics);
CREATE INDEX threads_remote_idx ON app_private.threads(candidate_id, remote_task_id);
CREATE INDEX events_thread_idx ON app_private.task_events(candidate_id, thread_id, status, created_at);
CREATE INDEX runs_group_idx ON app_private.ingest_runs(candidate_id, group_id, started_at);
CREATE INDEX feedback_label_idx ON app_private.quality_feedback(candidate_id, label);
CREATE INDEX emails_thread_idx ON app_private.emails(candidate_id, thread_id, message_index);

ALTER TABLE app_private.ingest_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.ingest_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.task_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.quality_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_private.chat_audit ENABLE ROW LEVEL SECURITY;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS app_private CASCADE")
