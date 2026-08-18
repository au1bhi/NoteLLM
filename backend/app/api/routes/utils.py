from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.api.deps import SessionDep
from app.models import RateLimitBucket

router = APIRouter(prefix="/utils", tags=["utils"])


@router.get("/health-check/")
async def health_check() -> bool:
    return True


@router.get("/readiness-check/")
def readiness_check(session: SessionDep) -> bool:
    """Report whether the database and current auth-protection schema are ready."""
    try:
        session.exec(select(RateLimitBucket.key).limit(1)).first()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="数据库或请求保护服务尚未就绪",
            headers={"Retry-After": "5"},
        ) from error
    return True
