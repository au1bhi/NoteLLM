from fastapi import APIRouter

from app.core.config import settings
from app.models import TurnstilePublic, WatermarkPublic

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/watermark", response_model=WatermarkPublic)
def get_watermark() -> WatermarkPublic:
    """The frontend watermark configuration.

    Public and unauthenticated: the watermark must render on login/signup too,
    and the text is server-authoritative so a rebuilt frontend cannot silently
    change it without also changing this setting. `enabled=false` tells the
    frontend to remove the watermark entirely (operator toggled via
    `WATERMARK_ENABLED` in the environment).
    """
    return WatermarkPublic(
        enabled=settings.WATERMARK_ENABLED, text=settings.WATERMARK_TEXT
    )


@router.get("/turnstile", response_model=TurnstilePublic)
def get_turnstile() -> TurnstilePublic:
    """Public widget configuration used before authentication."""
    return TurnstilePublic(
        enabled=settings.turnstile_enabled, site_key=settings.TURNSTILE_SITE_KEY
    )
