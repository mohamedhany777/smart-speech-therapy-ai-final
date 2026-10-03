from fastapi import APIRouter

from app.api.v1.endpoints import admin, assessments, auth, disorders, exercises, games, knowledge_base, notifications, therapy

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(disorders.router)
api_router.include_router(knowledge_base.router)
api_router.include_router(exercises.router)
api_router.include_router(games.router)
api_router.include_router(assessments.router)
api_router.include_router(therapy.router)
api_router.include_router(notifications.router)
