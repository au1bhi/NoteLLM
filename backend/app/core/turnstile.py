from collections.abc import Callable
from typing import Annotated, Any, Literal

import httpx
from fastapi import Header, HTTPException, Request

from app.core.config import settings
from app.core.rate_limit import client_ip

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_INVALID_DETAIL = "人机验证失败，请刷新后重试"
TurnstileAction = Literal["login", "signup", "password_recovery"]


def _verify_response(
    token: str, remote_ip: str, expected_action: TurnstileAction
) -> bool:
    """Validate one single-use Turnstile token with Cloudflare."""
    try:
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            response = client.post(
                _VERIFY_URL,
                data={
                    "secret": settings.TURNSTILE_SECRET_KEY,
                    "response": token,
                    "remoteip": remote_ip,
                },
                follow_redirects=False,
            )
        response.raise_for_status()
        payload: Any = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(
            status_code=503,
            detail="人机验证服务暂时不可用，请稍后重试",
        ) from error
    return (
        isinstance(payload, dict)
        and payload.get("success") is True
        and payload.get("action") == expected_action
        and payload.get("hostname") in settings.TURNSTILE_HOSTNAMES
    )


def require_turnstile(action: TurnstileAction) -> Callable[..., None]:
    """Bind each protected handler to its own action and deployment hosts."""

    def dependency(
        request: Request,
        token: Annotated[str | None, Header(alias="X-Turnstile-Token")] = None,
    ) -> None:
        if not settings.turnstile_enabled:
            return
        if not settings.TURNSTILE_HOSTNAMES:
            raise HTTPException(
                status_code=503, detail="人机验证配置不完整，请联系管理员"
            )
        if (
            not token
            or len(token) > 2048
            or not _verify_response(token, client_ip(request), action)
        ):
            raise HTTPException(status_code=400, detail=_INVALID_DETAIL)

    return dependency
