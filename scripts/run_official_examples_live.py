"""Run all 12 worked examples through the live local API and clean up exactly."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "mahendrushivam123@gmail.com"


def email(prefix: str, number: int, body: str, **overrides) -> dict:
    item = {
        "email_id": f"{prefix}-email-{number}",
        "thread_id": f"{prefix}-thread-{number}",
        "message_index": 0,
        "from_name": "Buyer",
        "from_email": "buyer@example.com",
        "to": "sales@example.com",
        "cc": [],
        "subject": f"Official example {number}",
        "body": body,
        "received_at": "2026-08-01T09:00:00+05:30",
        "attachments": [],
        "is_reply": False,
    }
    item.update(overrides)
    return item


def cases(prefix: str) -> tuple[list[dict], dict[int, dict | None], dict]:
    rows = [
        email(prefix, 1, "Meridian Steel invites proposals for an enterprise DMS covering 4 plants and ~1,200 users. Indicative budget is Rs. 25 lakhs. Proposals must reach us by 12th August 2026.", subject="RFP - Enterprise DMS for Meridian Steel", from_name="Meridian Steel Procurement", from_email="procurement@meridiansteel.in"),
        email(prefix, 2, "Hi, we're a 30-person logistics startup in Pune. Can we get a demo sometime next week? Nothing urgent. - Ankit Bose, Founder, Railyard Logistics", subject="Product demo", from_name="Ankit Bose", from_email="ankit@railyardlogistics.in"),
        email(prefix, 3, "Tender Notice No. BHEL/PROC/2026/0847. Bharat Heavy Electricals Limited invites bids for supply of analytics software licences. Estimated value: Rs. 6,50,000. Last date for bid submission: 03-08-2026, 1700 hrs IST.", subject="BHEL tender", received_at="2026-08-01T14:20:00+05:30", from_name="BHEL Procurement", from_email="procurement@bhel.in"),
        email(prefix, 4, "We're finalising sponsors for the India SaaS Summit in Bengaluru. Gold tier is ₹4,00,000 and includes a keynote slot. We need confirmation by tomorrow EOD as we're going to print. - Nandita Reddy, Sponsorship Lead", subject="India SaaS Summit sponsorship", received_at="2026-08-02T16:45:00+05:30", from_name="Nandita Reddy", from_email="nandita@indiasaasummit.in"),
        email(prefix, 5, "Please find attached invoice INV-2026-0331 for Rs. 1,18,000 (incl. 18% GST) against PO-88214. Kindly process - payment terms were Net 30 and this is now 12 days overdue. Also, our GSTIN has changed, updated details attached.", subject="Overdue invoice INV-2026-0331", from_name="Vantage Cloud Services", from_email="billing@vantagecloudservices.in", attachments=["INV-2026-0331.pdf"]),
        email(prefix, 6, "We're a Salesforce implementation partner across MEA with 40+ enterprise clients. We'd like to explore reselling your platform in the region, or a technical integration at minimum. Who handles partnerships?", subject="MEA reseller partnership", from_name="Zenith Cloud Partners", from_email="alliances@zenithcloudpartners.com"),
        email(prefix, 7, "I am out of office until 14th August with limited access to email. For urgent matters please contact my colleague at raghav@northbridge.in.", subject="Automatic reply: Out of office", from_email="person@northbridge.in"),
        email(prefix, 8, "Hi, I noticed your website isn't ranking on page 1 for key terms. We've helped 200+ SaaS companies 3x their organic traffic. We do content marketing, PR outreach, and webinar promotion. Free audit attached - interested in a quick 15 min call?", subject="Free SEO audit", from_email="sales@seovendor.example", attachments=["free-audit.pdf"]),
        email(prefix, 9, "The B2B Growth Weekly - Issue #212. In this edition: why PLG is stalling, 5 pricing experiments that worked, and a teardown of Figma's onboarding. [Unsubscribe]", subject="B2B Growth Weekly newsletter"),
        email(prefix, 11, "Hi - we met at your booth in Mumbai. Two things: (1) we'd like to evaluate your platform for our 800-person org, budget TBD but likely significant, and (2) our CMO wants to co-host a webinar with your team in September. Can you loop in the right people? - Farhan Qureshi, VP Strategy, Halcyon Retail", subject="Platform evaluation and webinar", from_name="Farhan Qureshi", from_email="farhan@halcyonretail.in"),
        email(prefix, 12, "Bhai, humko aapka product chahiye for our dealer network. Around 150 users honge. Budget approx 1.2 cr allocated hai for this FY. Kab connect kar sakte hain? Thoda jaldi, board review 20th ko hai.", subject="Product requirement", received_at="2026-08-05T09:00:00+05:30", from_name="Amit", from_email="amit@gmail.com"),
    ]
    expected = {
        1: {"assignee_id": "u_aarti", "category": "enterprise_rfp", "priority": "medium", "due_date": "2026-08-12", "deal_value_inr": 2_500_000, "company_name": "Meridian Steel"},
        2: {"assignee_id": "u_rohit", "category": "smb_enquiry", "priority": "low", "due_date": None, "deal_value_inr": None, "company_name": "Railyard Logistics"},
        3: {"assignee_id": "u_aarti", "category": "enterprise_rfp", "priority": "high", "due_date": "2026-08-03", "deal_value_inr": 650_000, "company_name": "Bharat Heavy Electricals Limited"},
        4: {"assignee_id": "u_meera", "category": "marketing", "priority": "high", "due_date": "2026-08-03", "deal_value_inr": 400_000, "company_name": "India SaaS Summit"},
        5: {"assignee_id": "u_divya", "category": "finance", "priority": "high", "due_date": None, "deal_value_inr": None, "company_name": "Vantage Cloud Services"},
        6: {"assignee_id": "u_karan", "category": "alliances", "priority": "medium", "due_date": None, "deal_value_inr": None, "company_name": "Zenith Cloud Partners"},
        7: None,
        8: None,
        9: None,
        11: {"assignee_id": "u_triage", "category": "triage", "priority": "medium", "due_date": None, "deal_value_inr": None, "company_name": "Halcyon Retail", "confidence": 0.42},
        12: {"assignee_id": "u_aarti", "category": "enterprise_rfp", "priority": "medium", "due_date": "2026-08-20", "deal_value_inr": 12_000_000, "company_name": None},
    }
    reply = email(prefix, 10, "Correction to our earlier note - the board has approved an increased budget of Rs. 32 lakhs, and the submission deadline is advanced to 11th August. Apologies for the change.\n\nOn 1 Aug 2026 wrote:\nIndicative budget is Rs. 25 lakhs; deadline 12th August.", subject="Re: RFP - Enterprise DMS for Meridian Steel", received_at="2026-08-09T09:00:00+05:30", thread_id=f"{prefix}-thread-1", message_index=1, is_reply=True, from_name="Meridian Steel Procurement", from_email="procurement@meridiansteel.in")
    return rows, expected, reply


def compare(number: int, actual: dict | None, expected: dict | None) -> dict:
    if expected is None:
        return {"example": number, "passed": actual is None, "expected": "no task", "actual": actual}
    fields = {key: actual.get(key) if actual else None for key in expected}
    mismatches = {key: {"expected": value, "actual": fields[key]} for key, value in expected.items() if fields[key] != value}
    return {"example": number, "passed": not mismatches, "expected": expected, "actual": fields, "mismatches": mismatches}


def cleanup(prefix: str, batch_id: str, run_ids: list[str]) -> None:
    if not prefix.startswith("official-live-"):
        raise RuntimeError("refusing unscoped cleanup")
    values = dotenv_values(ROOT / ".env")
    url = str(values.get("SUPABASE_DB_URL") or "")
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    like = prefix + "%"
    with psycopg.connect(url, connect_timeout=10) as connection:
        connection.execute("DELETE FROM app_private.chat_audit WHERE candidate_id=%s AND scope_id=%s", (CANDIDATE_ID, batch_id))
        connection.execute("DELETE FROM app_private.quality_feedback WHERE candidate_id=%s AND email_id LIKE %s", (CANDIDATE_ID, like))
        connection.execute("DELETE FROM app_private.task_events WHERE candidate_id=%s AND email_id LIKE %s", (CANDIDATE_ID, like))
        connection.execute("DELETE FROM app_private.decisions WHERE candidate_id=%s AND email_id LIKE %s", (CANDIDATE_ID, like))
        connection.execute("DELETE FROM app_private.emails WHERE candidate_id=%s AND email_id LIKE %s", (CANDIDATE_ID, like))
        connection.execute("DELETE FROM app_private.threads WHERE candidate_id=%s AND thread_id LIKE %s", (CANDIDATE_ID, like))
        connection.execute("DELETE FROM app_private.tasks WHERE candidate_id=%s AND thread_id LIKE %s", (CANDIDATE_ID, like))
        connection.execute(
            "DELETE FROM app_private.ingest_runs WHERE group_id IN (SELECT id FROM app_private.ingest_groups WHERE candidate_id=%s AND client_batch_id=%s)",
            (CANDIDATE_ID, batch_id),
        )
        connection.execute("DELETE FROM app_private.ingest_groups WHERE candidate_id=%s AND client_batch_id=%s", (CANDIDATE_ID, batch_id))
        connection.commit()
        remaining = connection.execute(
            "SELECT (SELECT count(*) FROM app_private.tasks WHERE thread_id LIKE %s) + (SELECT count(*) FROM app_private.emails WHERE email_id LIKE %s)",
            (like, like),
        ).fetchone()[0]
        if remaining:
            raise RuntimeError(f"official-example cleanup left {remaining} rows")


def main() -> None:
    prefix = "official-live-" + uuid4().hex
    batch_id = str(uuid4())
    rows, expected, reply = cases(prefix)
    run_ids: list[str] = []
    results: list[dict] = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=300) as client:
        try:
            first = client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "client_batch_id": batch_id, "source": "api", "emails": rows})
            first.raise_for_status()
            run_ids.append(first.json()["run_id"])
            for number in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12):
                tasks = client.get("/tasks", params={"candidate_id": CANDIDATE_ID, "thread_id": f"{prefix}-thread-{number}"}).json()
                results.append(compare(number, tasks[0] if len(tasks) == 1 else None, expected[number]))

            update = client.post("/ingest", json={"candidate_id": CANDIDATE_ID, "client_batch_id": batch_id, "source": "api", "emails": [reply]})
            update.raise_for_status()
            run_ids.append(update.json()["run_id"])
            updated = client.get("/tasks", params={"candidate_id": CANDIDATE_ID, "thread_id": f"{prefix}-thread-1"}).json()
            expected_update = {"priority": "high", "due_date": "2026-08-11", "deal_value_inr": 3_200_000, "source_email_id": f"{prefix}-email-1"}
            results.append(compare(10, updated[0] if len(updated) == 1 else None, expected_update))
        finally:
            cleanup(prefix, batch_id, run_ids)

    results.sort(key=lambda row: row["example"])
    report = {"model": dotenv_values(ROOT / ".env").get("GEMINI_MODEL"), "passed": sum(row["passed"] for row in results), "total": 12, "results": results, "cleanup_verified": True}
    target = ROOT / "artifacts" / "official_examples_live.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["passed"] != 12:
        raise SystemExit("One or more official worked examples failed")


if __name__ == "__main__":
    main()
