from datetime import datetime,timezone
from backend.app.domain.email_models import EmailMessage
from backend.app.domain.enums import AssigneeId,Category
from backend.app.domain.routing_policy import route_email
from backend.app.services.email_normalizer import normalize_email
from backend.app.services.gemini_extractor import heuristic_extract

def email(body:str,subject:str="Pricing request"):
    return EmailMessage(email_id="e1",thread_id="t1",message_index=0,from_name="Buyer",from_email="buyer@example.com",to="sales@example.com",cc=[],subject=subject,body=body,received_at=datetime(2026,1,1,tzinfo=timezone.utc),attachments=[],is_reply=False)
def test_exact_threshold_routes_rohit():
    msg=normalize_email(email("We need a quote with a budget of INR 10 lakh."));decision=route_email(msg,heuristic_extract(msg));assert decision.task.assignee_id==AssigneeId.ROHIT;assert decision.task.category==Category.SMB_ENQUIRY
def test_above_threshold_routes_aarti():
    msg=normalize_email(email("We want to purchase licences for INR 10,00,001."));decision=route_email(msg,heuristic_extract(msg));assert decision.task.assignee_id==AssigneeId.AARTI
