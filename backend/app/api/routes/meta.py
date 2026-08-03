from fastapi import APIRouter

from app.core.config import settings
from app.models import WatermarkPublic

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/watermark", response_model=WatermarkPublic)
def get_watermark() -> WatermarkPublic:
    """The frontend watermark text.

    Public and unauthenticated: the watermark must render on login/signup too,
    and the text is server-authoritative so a rebuilt frontend cannot silently
    change it without also changing this setting.
    """
    return WatermarkPublic(text=settings.WATERMARK_TEXT)
