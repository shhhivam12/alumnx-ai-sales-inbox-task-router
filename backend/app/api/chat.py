from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends

from backend.app.config import get_settings
from backend.app.dependencies import get_store
from backend.app.domain.chat_models import ChatRequest, ChatResponse
from backend.app.repositories.store import MemoryStore
from backend.app.services.answer_renderer import render_answer
from backend.app.services.chat_answer_service import ChatAnswerService
from backend.app.services.chat_executor import execute_plan
from backend.app.services.chat_planner import plan_question

router = APIRouter(tags=["chat"])


@lru_cache
def get_chat_answer_service() -> ChatAnswerService:
    return ChatAnswerService(get_settings())


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    store: MemoryStore = Depends(get_store),
    answer_service: ChatAnswerService = Depends(get_chat_answer_service),
) -> ChatResponse:
    plan = plan_question(payload.query)
    plan = answer_service.plan(payload.query, plan)
    data = execute_plan(store, plan, payload.scope)
    answer, status = render_answer(plan, data)
    answer = answer_service.phrase(plan, data, answer)
    store.add_chat_audit({"scope_type": payload.scope.type, "scope_id": payload.scope.id, "question": payload.query, "validated_plan": plan.model_dump(), "supporting_data": data, "answer": answer, "status": status, "created_at": datetime.now(timezone.utc).isoformat()})
    return ChatResponse(answer=answer, supporting_data=data, scope=payload.scope)
