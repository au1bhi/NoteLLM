from fastapi import APIRouter

from app.api.routes import conversations, items, login, notebooks, private, users, utils
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(notebooks.router)
api_router.include_router(conversations.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
