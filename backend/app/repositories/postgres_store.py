from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from psycopg import Connection

from backend.app.config import LOCKED_CANDIDATE_ID
from backend.app.db.pool import DatabasePool
from backend.app.domain.email_models import NormalizedEmail
from backend.app.domain.task_models import RoutingDecision, TaskPatch, TaskPayload, TaskRecord
from backend.app.errors import AppError


class PostgresStore:
    def __init__(self, pool: DatabasePool) -> None:
        self.pool = pool
        self.pool.open()
        self._bound_connection: ContextVar[Connection | None] = ContextVar("thread_transaction", default=None)

    @contextmanager
    def _connection(self) -> Iterator[tuple[Connection, bool]]:
        bound = self._bound_connection.get()
        if bound is not None:
            yield bound, False
            return
        with self.pool.connection() as connection:
            yield connection, True

    def health(self) -> bool: return self.pool.health()
    def migration_ready(self) -> bool: return self.pool.migration_ready()

    @staticmethod
    def _task_row(row: dict[str, Any]) -> dict[str, Any]:
        """Convert database-native dates/decimals into the public JSON contract."""
        return TaskRecord.model_validate(row).model_dump(mode="json")

    def list_tasks(
        self,
        candidate_id: str,
        *,
        thread_id: str | None = None,
        source_email_id: str | None = None,
        assignee_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = ["candidate_id=%s"], [candidate_id]
        for field, value in (
            ("thread_id", thread_id),
            ("source_email_id", source_email_id),
            ("assignee_id", assignee_id),
        ):
            if value:
                where.append(f"{field}=%s")
                params.append(value)
        sql = "SELECT * FROM app_private.tasks WHERE " + " AND ".join(where) + " ORDER BY created_at,task_id"
        with self._connection() as (conn, _), conn.cursor() as cur:
            cur.execute(sql, params)
            return [self._task_row(dict(row)) for row in cur.fetchall()]

    def create_task(self, payload: TaskPayload) -> dict[str, Any]:
        task_id = f"tsk_{uuid4().hex[:16]}"
        values = payload.model_dump(mode="python")
        with self._connection() as (conn, owns_connection), conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app_private.tasks(
                    task_id,candidate_id,source_email_id,thread_id,title,description,
                    assignee_id,category,priority,due_date,deal_value_inr,company_name,
                    confidence,created_at,updated_at
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
                RETURNING *""",
                (
                    task_id, values["candidate_id"], values["source_email_id"],
                    values["thread_id"], values["title"], values["description"],
                    values["assignee_id"], values["category"], values["priority"],
                    values["due_date"], values["deal_value_inr"], values["company_name"],
                    values["confidence"],
                ),
            )
            row = self._task_row(dict(cur.fetchone()))
            if owns_connection:
                conn.commit()
            return row

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._connection() as (conn, _), conn.cursor() as cur:
            cur.execute("SELECT * FROM app_private.tasks WHERE task_id=%s", (task_id,))
            row = cur.fetchone()
            return self._task_row(dict(row)) if row else None

    def patch_task(self, task_id: str, patch: TaskPatch) -> dict[str, Any]:
        changes = patch.model_dump(mode="python", exclude_unset=True)
        allowed = {
            "title", "description", "assignee_id", "category", "priority",
            "due_date", "deal_value_inr", "company_name", "confidence",
        }
        fields = [field for field in changes if field in allowed]
        assignments = ",".join(f"{field}=%s" for field in fields)
        params = [changes[field] for field in fields] + [task_id]
        with self._connection() as (conn, owns_connection), conn.cursor() as cur:
            cur.execute(
                f"UPDATE app_private.tasks SET {assignments},updated_at=now() WHERE task_id=%s RETURNING *",
                params,
            )
            row = cur.fetchone()
            if not row:
                raise AppError("task_not_found", "task was not found", status_code=404)
            if owns_connection:
                conn.commit()
            return self._task_row(dict(row))

    def delete_task(self, task_id: str) -> bool:
        with self._connection() as (conn, owns_connection), conn.cursor() as cur:
            cur.execute("DELETE FROM app_private.tasks WHERE task_id=%s RETURNING task_id", (task_id,))
            removed = cur.fetchone() is not None
            if removed:
                cur.execute(
                    """UPDATE app_private.threads
                    SET remote_task_id=NULL,current_task_snapshot=NULL,
                        reconciliation_status='empty',updated_at=now()
                    WHERE remote_task_id=%s""",
                    (task_id,),
                )
            if owns_connection:
                conn.commit()
            return removed

    def start_run(self, client_batch_id: UUID | None, source: str, request_hash: str, count: int) -> str:
        run_id, group_id = uuid4(), None
        with self.pool.connection() as conn, conn.cursor() as cur:
            if client_batch_id:
                cur.execute("INSERT INTO app_private.ingest_groups(id,candidate_id,client_batch_id,source) VALUES(%s,%s,%s,%s) ON CONFLICT(candidate_id,client_batch_id) DO UPDATE SET source=EXCLUDED.source RETURNING id", (uuid4(), LOCKED_CANDIDATE_ID, client_batch_id, source))
                group_id = cur.fetchone()["id"]
            cur.execute("INSERT INTO app_private.ingest_runs(id,group_id,candidate_id,request_hash,status,received_count,started_at) VALUES(%s,%s,%s,%s,'processing',%s,now())", (run_id, group_id, LOCKED_CANDIDATE_ID, request_hash, count))
            conn.commit()
        return str(run_id)

    def finish_run(self, run_id: str, counters: dict[str, int], errors: list[dict[str, Any]]) -> None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE app_private.ingest_runs SET status=%s,processed=%s,tasks_created=%s,tasks_updated=%s,skipped=%s,unchanged=%s,errors=%s,completed_at=now() WHERE id=%s", ("failed" if errors else "completed", counters["processed"], counters["tasks_created"], counters["tasks_updated"], counters["skipped"], counters["unchanged"], Jsonb(errors), run_id)); conn.commit()

    def inspect_email(self, message: NormalizedEmail) -> str:
        with self._connection() as (conn, _), conn.cursor() as cur:
            cur.execute("SELECT email_id,content_hash FROM app_private.emails WHERE candidate_id=%s AND (email_id=%s OR (thread_id=%s AND message_index=%s))", (LOCKED_CANDIDATE_ID, message.email.email_id, message.email.thread_id, message.email.message_index))
            for row in cur.fetchall():
                if row["email_id"] == message.email.email_id:
                    if row["content_hash"] != message.content_hash: raise AppError("email_id_content_conflict", "stored email_id has different content", status_code=409)
                    return "unchanged"
                raise AppError("thread_index_conflict", "thread/message_index already belongs to another email", status_code=409)
        return "new"

    @contextmanager
    def thread_lock(self, thread_id: str) -> Iterator[None]:
        with self.pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute(
                """INSERT INTO app_private.threads(
                    id,candidate_id,thread_id,last_message_index,message_count,update_count,
                    reconciliation_status,created_at,updated_at
                ) VALUES(%s,%s,%s,-1,0,0,'empty',now(),now())
                ON CONFLICT(candidate_id,thread_id) DO NOTHING""",
                (uuid4(), LOCKED_CANDIDATE_ID, thread_id),
            )
            cur.execute(
                "SELECT id FROM app_private.threads WHERE candidate_id=%s AND thread_id=%s FOR UPDATE",
                (LOCKED_CANDIDATE_ID, thread_id),
            )
            token = self._bound_connection.set(conn)
            try:
                yield None
            finally:
                self._bound_connection.reset(token)

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._connection() as (conn, _), conn.cursor() as cur:
            cur.execute("SELECT * FROM app_private.threads WHERE candidate_id=%s AND thread_id=%s", (LOCKED_CANDIDATE_ID, thread_id)); row = cur.fetchone(); return dict(row) if row else None

    def save_outcome(self, message: NormalizedEmail, decision: RoutingDecision, run_id: str, remote: dict[str, Any] | None, event: dict[str, Any] | None) -> None:
        email_row_id, decision_id = uuid4(), uuid4(); task = decision.task.model_dump(mode="json") if decision.task else {}
        remote_task_id = (remote or {}).get("task_id") or (remote or {}).get("id")
        with self._connection() as (conn, owns_connection), conn.cursor() as cur:
            cur.execute("INSERT INTO app_private.emails(id,candidate_id,email_id,thread_id,message_index,raw_email,content_hash,normalized_body,latest_reply_body,received_at,first_seen_run_id,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())", (email_row_id, LOCKED_CANDIDATE_ID, message.email.email_id, message.email.thread_id, message.email.message_index, Jsonb(message.email.model_dump(mode="json")), message.content_hash, message.normalized_body, message.latest_reply_body, message.email.received_at, run_id))
            cur.execute("""INSERT INTO app_private.decisions(id,email_row_id,candidate_id,email_id,thread_id,operation,decision_status,actionability,skip_reason,assignee_id,category,priority,deadline_at,due_date,deal_value_inr,company_name,confidence,primary_intents,topics,intent_direction,organization_type,alliance_subtype,marketing_subtype,amount_mentions,deadline_mentions,reasoning,evidence,degraded_mode,model_name,prompt_version,remote_task_id,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,'reconciled',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())""", (decision_id,email_row_id,LOCKED_CANDIDATE_ID,decision.email_id,decision.thread_id,decision.operation.value,decision.actionability.value,decision.skip_reason.value if decision.skip_reason else None,task.get("assignee_id"),task.get("category"),task.get("priority"),decision.deadline_at,task.get("due_date"),task.get("deal_value_inr"),task.get("company_name"),decision.confidence,Jsonb(decision.primary_intents),decision.topics,decision.intent_direction,decision.organization_type,decision.alliance_subtype,decision.marketing_subtype,Jsonb(decision.amount_mentions),Jsonb(decision.deadline_mentions),decision.reasoning,Jsonb(decision.evidence),decision.degraded_mode,decision.model_name,decision.prompt_version,remote_task_id))
            cur.execute("""INSERT INTO app_private.threads(id,candidate_id,thread_id,remote_task_id,source_email_id,current_task_snapshot,last_message_index,message_count,update_count,reconciliation_status,created_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,1,%s,%s,now(),now()) ON CONFLICT(candidate_id,thread_id) DO UPDATE SET remote_task_id=COALESCE(EXCLUDED.remote_task_id,app_private.threads.remote_task_id),source_email_id=COALESCE(app_private.threads.source_email_id,EXCLUDED.source_email_id),current_task_snapshot=COALESCE(EXCLUDED.current_task_snapshot,app_private.threads.current_task_snapshot),last_message_index=GREATEST(app_private.threads.last_message_index,EXCLUDED.last_message_index),message_count=app_private.threads.message_count+1,update_count=app_private.threads.update_count+EXCLUDED.update_count,reconciliation_status=EXCLUDED.reconciliation_status,updated_at=now()""", (uuid4(),LOCKED_CANDIDATE_ID,message.email.thread_id,remote_task_id,(remote or {}).get("source_email_id"),Jsonb(remote) if remote else None,message.email.message_index,1 if decision.operation.value=="update" and event else 0,"mapped" if remote else "empty"))
            if event:
                cur.execute("""INSERT INTO app_private.task_events(id,operation_key,candidate_id,thread_id,email_id,remote_task_id,event_type,status,before_snapshot,patch,after_snapshot,attempt_count,created_at,confirmed_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)""", (event["id"],event["operation_key"],LOCKED_CANDIDATE_ID,event["thread_id"],event["email_id"],event.get("remote_task_id"),event["event_type"],event["status"],Jsonb(event["before_snapshot"]) if event.get("before_snapshot") else None,Jsonb(event["patch"]) if event.get("patch") else None,Jsonb(event["after_snapshot"]) if event.get("after_snapshot") else None,event["attempt_count"],event.get("confirmed_at")))
            if owns_connection:
                conn.commit()

    def list_decisions(self, scope_type: str = "all", scope_id: str | None = None) -> list[dict[str, Any]]:
        where, params = ["d.candidate_id=%s"], [LOCKED_CANDIDATE_ID]
        if scope_type == "run": where.append("e.first_seen_run_id=%s"); params.append(scope_id)
        if scope_type == "batch": where.append("g.client_batch_id=%s"); params.append(scope_id)
        sql = """SELECT d.*,e.first_seen_run_id AS run_id,g.client_batch_id FROM app_private.decisions d JOIN app_private.emails e ON e.id=d.email_row_id JOIN app_private.ingest_runs r ON r.id=e.first_seen_run_id LEFT JOIN app_private.ingest_groups g ON g.id=r.group_id WHERE """ + " AND ".join(where) + " ORDER BY e.thread_id,e.message_index,d.created_at"
        with self.pool.connection() as conn, conn.cursor() as cur: cur.execute(sql, params); rows=cur.fetchall()
        result=[]
        for r in rows:
            row=dict(r); task=None
            if row.get("confidence") is not None:
                row["confidence"] = float(row["confidence"])
            if row.get("category"): task={k:row.get(k) for k in ("assignee_id","category","priority","due_date","deal_value_inr","company_name","confidence")} | {"source_email_id": row["email_id"], "thread_id":row["thread_id"]}
            row["task"],row["run_id"],row["client_batch_id"]=task,str(row["run_id"]),str(row["client_batch_id"]) if row.get("client_batch_id") else None
            result.append(row)
        return result

    def list_threads(self) -> list[dict[str, Any]]:
        with self.pool.connection() as c,c.cursor() as x:x.execute("SELECT * FROM app_private.threads WHERE candidate_id=%s",(LOCKED_CANDIDATE_ID,));return [dict(r) for r in x.fetchall()]
    def list_events(self) -> list[dict[str, Any]]:
        with self.pool.connection() as c,c.cursor() as x:x.execute("SELECT * FROM app_private.task_events WHERE candidate_id=%s",(LOCKED_CANDIDATE_ID,));return [dict(r) for r in x.fetchall()]
    def list_runs(self, scope_type: str="all", scope_id: str|None=None) -> list[dict[str, Any]]:
        sql="SELECT r.*,g.client_batch_id FROM app_private.ingest_runs r LEFT JOIN app_private.ingest_groups g ON g.id=r.group_id WHERE r.candidate_id=%s";params=[LOCKED_CANDIDATE_ID]
        if scope_type=="run":sql+=" AND r.id=%s";params.append(scope_id)
        if scope_type=="batch":sql+=" AND g.client_batch_id=%s";params.append(scope_id)
        with self.pool.connection() as c,c.cursor() as x:x.execute(sql,params);return [dict(r) for r in x.fetchall()]
    def set_feedback(self,email_id:str,label:str,note:str|None)->dict[str,Any]:
        with self.pool.connection() as c,c.cursor() as x:
            x.execute("SELECT 1 FROM app_private.decisions WHERE candidate_id=%s AND email_id=%s",(LOCKED_CANDIDATE_ID,email_id))
            if not x.fetchone():
                raise AppError("decision_not_found","email decision not found",status_code=404)
            x.execute("INSERT INTO app_private.quality_feedback(id,candidate_id,email_id,label,note,created_at) VALUES(%s,%s,%s,%s,%s,now()) ON CONFLICT(candidate_id,email_id) DO UPDATE SET label=EXCLUDED.label,note=EXCLUDED.note RETURNING *",(uuid4(),LOCKED_CANDIDATE_ID,email_id,label,note));row=dict(x.fetchone());c.commit();return row
    def list_feedback(self)->list[dict[str,Any]]:
        with self.pool.connection() as c,c.cursor() as x:x.execute("SELECT * FROM app_private.quality_feedback WHERE candidate_id=%s",(LOCKED_CANDIDATE_ID,));return [dict(r) for r in x.fetchall()]
    def add_chat_audit(self,row:dict[str,Any])->None:
        with self.pool.connection() as c,c.cursor() as x:x.execute("INSERT INTO app_private.chat_audit(id,candidate_id,scope_type,scope_id,question,validated_plan,supporting_data,answer,status,prompt_version,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'chat-v1',now())",(uuid4(),LOCKED_CANDIDATE_ID,row["scope_type"],row.get("scope_id"),row["question"],Jsonb(row["validated_plan"]),Jsonb(row["supporting_data"]),row["answer"],row["status"]));c.commit()
