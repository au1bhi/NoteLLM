import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, delete, func, select

from app import crud
from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
)
from app.core.config import settings
from app.core.rate_limit import rate_limit
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    get_password_hash,
    verify_password,
)
from app.core.ssrf import validate_outbound_url
from app.models import (
    Item,
    Message,
    ModelFetchRequest,
    ModelInfoPublic,
    UpdatePassword,
    User,
    UserCreate,
    UserProviderSettings,
    UserProviderSettingsCreate,
    UserProviderSettingsPublic,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
    UserUsagePublic,
    get_datetime_utc,
)
from app.services.provider_settings import (
    load_user_provider_settings,
    mask_secret,
)
from app.services.usage import quota_status
from app.utils import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users.
    """

    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = (
        select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    )
    users = session.exec(statement).all()

    users_public = [UserPublic.model_validate(user) for user in users]
    return UsersPublic(data=users_public, count=count)


@router.post(
    "/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic
)
def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Create new user.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="该邮箱的用户已存在于系统中。",
        )

    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """

    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(status_code=409, detail="该邮箱的用户已存在")
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.patch(
    "/me/password",
    response_model=Message,
    dependencies=[Depends(rate_limit(limit=10, window=60))],
)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="密码错误")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="密码更新成功")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.get("/me/usage", response_model=UserUsagePublic)
def read_user_usage(session: SessionDep, current_user: CurrentUser) -> UserUsagePublic:
    """
    Get the current user's usage plus the free allowance that applies to each
    dimension. `chat_quota`/`embedding_quota` are None when the user brings
    their own API key or when nothing is configured.
    """
    status = quota_status(session, current_user.id)
    return UserUsagePublic(
        chat_tokens=status.chat_tokens,
        chat_quota=status.chat_quota,
        chat_source=status.chat_source,
        embedding_chars=status.embedding_chars,
        embedding_quota=status.embedding_quota,
        embedding_source=status.embedding_source,
        period_start=status.period_start,
    )


@router.delete("/me", response_model=Message)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(status_code=403, detail="超级管理员不能删除自己")
    session.delete(current_user)
    session.commit()
    return Message(message="用户删除成功")


def _cooldown_until(
    settings_row: UserProviderSettings | None,
) -> datetime | None:
    """When the user may switch back to server-default billing, or None.

    The switch-back window opens when a user configures their own API key and
    closes 24 hours later (PROVIDER_SWITCH_COOLDOWN_HOURS). Users without an
    own key have nothing to switch back from, so no cooldown applies.
    """
    if (
        settings_row is None
        or settings_row.provider_changed_at is None
        or not (settings_row.chat_api_key or settings_row.embedding_api_key)
    ):
        return None
    expires = settings_row.provider_changed_at + timedelta(
        hours=settings.PROVIDER_SWITCH_COOLDOWN_HOURS
    )
    if expires <= datetime.now(UTC):
        return None
    return expires


def _cooldown_detail(until: datetime) -> str:
    remaining = until - datetime.now(UTC)
    total_minutes = max(1, int(remaining.total_seconds()) // 60)
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"切换回系统 API 需等待冷却，还需 {hours} 小时 {minutes} 分钟后可操作"
    return f"切换回系统 API 需等待冷却，还需 {minutes} 分钟后可操作"


def _provider_settings_public(
    settings_row: UserProviderSettings | None,
) -> UserProviderSettingsPublic:
    if settings_row is None:
        return UserProviderSettingsPublic()

    def masked(field: str) -> str:
        value = getattr(settings_row, field)
        if not value:
            return ""
        return mask_secret(decrypt_secret(value))

    return UserProviderSettingsPublic(
        chat_base_url=settings_row.chat_base_url,
        chat_api_key=masked("chat_api_key"),
        chat_model=settings_row.chat_model,
        embedding_base_url=settings_row.embedding_base_url,
        embedding_api_key=masked("embedding_api_key"),
        embedding_model=settings_row.embedding_model,
        cooldown_until=_cooldown_until(settings_row),
    )


@router.get("/me/provider-settings", response_model=UserProviderSettingsPublic)
def read_user_provider_settings(
    session: SessionDep, current_user: CurrentUser
) -> UserProviderSettingsPublic:
    """
    Get the current user's own LLM/embedding provider settings (keys masked).
    """
    settings_row = load_user_provider_settings(session, current_user.id)
    return _provider_settings_public(settings_row)


@router.put("/me/provider-settings", response_model=UserProviderSettingsPublic)
def upsert_user_provider_settings(
    session: SessionDep,
    current_user: CurrentUser,
    settings_in: UserProviderSettingsCreate,
) -> UserProviderSettingsPublic:
    """
    Save the current user's provider settings. An empty API key keeps the
    stored key; empty base_url/model fall back to the server defaults.
    """
    settings_row = load_user_provider_settings(session, current_user.id)
    if settings_row is None:
        settings_row = UserProviderSettings(user_id=current_user.id)
        session.add(settings_row)

    data = settings_in.model_dump(exclude_unset=True)
    for field in ("chat_api_key", "embedding_api_key"):
        if field in data:
            if data[field]:
                data[field] = encrypt_secret(data[field])
            else:
                data.pop(field)
    # Configuring an own key opens the switch-back cooldown window.
    if data.get("chat_api_key") or data.get("embedding_api_key"):
        settings_row.provider_changed_at = get_datetime_utc()
    for field in (
        "chat_base_url",
        "chat_model",
        "embedding_base_url",
        "embedding_model",
    ):
        if field in data and not data[field]:
            data[field] = None
    settings_row.sqlmodel_update(data)
    settings_row.updated_at = get_datetime_utc()
    session.add(settings_row)
    session.commit()
    session.refresh(settings_row)
    return _provider_settings_public(settings_row)


@router.delete("/me/provider-settings", response_model=Message)
def delete_user_provider_settings(
    session: SessionDep, current_user: CurrentUser
) -> Message:
    """
    Clear the current user's provider settings, reverting to server defaults.
    Blocked by the switch-back cooldown for 24h after configuring an own key.
    """
    settings_row = load_user_provider_settings(session, current_user.id)
    cooldown_until = _cooldown_until(settings_row)
    if cooldown_until is not None:
        raise HTTPException(
            status_code=429, detail=_cooldown_detail(cooldown_until)
        )
    if settings_row is not None:
        session.delete(settings_row)
        session.commit()
    return Message(message="已清除模型配置")


@router.post(
    "/me/provider-settings/models",
    response_model=list[ModelInfoPublic],
)
def fetch_available_models(
    body: ModelFetchRequest,
    _current_user: CurrentUser,
) -> list[ModelInfoPublic]:
    """
    Fetch the model IDs available on an OpenAI-compatible endpoint. Empty
    base_url/api_key fall back to the server's configured LLM provider; a
    user-supplied base_url is validated against internal-network targets.
    Keys are used once for this request and are never stored.
    """
    server_base = str(settings.LLM_BASE_URL) if settings.LLM_BASE_URL else ""
    server_key = settings.LLM_API_KEY or ""
    user_base = body.base_url.strip()
    user_key = body.api_key.strip()
    if user_base and not user_key:
        # Never send the server's key to a custom endpoint the user controls.
        raise HTTPException(
            status_code=422,
            detail="自定义 Base URL 需要同时提供 API Key",
        )
    base_url = user_base or server_base
    api_key = user_key or server_key
    if user_base:
        base_url = validate_outbound_url(base_url)
    if not base_url or not api_key:
        raise HTTPException(
            status_code=422,
            detail="请先配置 API Key，或使用服务端默认配置",
        )
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as error:
        raise HTTPException(
            status_code=503,
            detail="无法获取模型，请检查 Base URL 与 API Key 是否正确",
        ) from error
    data = payload.get("data", []) if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail="模型提供方返回了异常数据")
    model_ids = [
        item.get("id")
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ][:100]
    if not model_ids:
        raise HTTPException(status_code=502, detail="模型提供方未返回任何模型")
    return [ModelInfoPublic(id=model_id) for model_id in model_ids]


@router.post(
    "/signup",
    response_model=UserPublic,
    dependencies=[Depends(rate_limit(limit=5, window=60))],
)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="该邮箱的用户已存在于系统中",
        )
    user_create = UserCreate.model_validate(user_in)
    user = crud.create_user(session=session, user_create=user_create)
    return user


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id.
    """
    user = session.get(User, user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="该用户权限不足",
        )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


@router.patch(
    "/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="系统中不存在该 ID 的用户",
        )
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(status_code=409, detail="该邮箱的用户已存在")

    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return db_user


@router.delete("/{user_id}", dependencies=[Depends(get_current_active_superuser)])
def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user == current_user:
        raise HTTPException(status_code=403, detail="超级管理员不能删除自己")
    statement = delete(Item).where(col(Item.owner_id) == user_id)
    session.exec(statement)
    session.delete(user)
    session.commit()
    return Message(message="用户删除成功")
