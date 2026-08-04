from fastapi import APIRouter

from app.api.routes import (
    conversations,
    login,
    meta,
    notebooks,
    study_plans,
    users,
    utils,
)

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(meta.router)
api_router.include_router(notebooks.router)
api_router.include_router(conversations.router)
api_router.include_router(study_plans.router)
