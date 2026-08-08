from fastapi import APIRouter

from backend.app.api import chat, config, decisions, grader_tasks, health, ingest, samples, stats, tasks

api_router = APIRouter()
for router in (config.router, decisions.router, samples.router, stats.router, tasks.router, chat.router):
    api_router.include_router(router, prefix="/api")
api_router.include_router(ingest.router)
api_router.include_router(health.router)
api_router.include_router(grader_tasks.router)
