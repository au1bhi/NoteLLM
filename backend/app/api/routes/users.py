import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, func, select

from app import crud
from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
)
from app.core.config import settings
from app.core.rate_limit import rate_limit, recipient_send_cooldown
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
    get_password_hash,
    verify_password,
)
from app.core.ssrf import pinned_request, validate_outbound_url
from app.core.turnstile import require_turnstile
from app.models import (
    Message,
    ModelFetchRequest,
    ModelInfoPublic,
    ResendVerificationRequest,
    SignupResult,
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
    UserUsage,
    UserUsagePublic,
    VerifyEmailRequest,
    get_datetime_utc,
)
from app.services.provider_settings import (
    load_user_provider_settings,
    mask_secret,
    resolve_api_base,
)
from app.services.sources import delete_owner_upload_files
from app.services.usage import (
    QuotaError,
    quota_status,
    restore_tombstone_usage,
    save_usage_tombstone,
    usage_reservation,
)
from app.utils import (
    allowed_email_domains_text,
    canonical_email,
    email_change_token_account,
    email_change_token_password_changed_at,
    generate_email_change_token,
    generate_new_account_email,
    generate_verify_email_email,
    is_allowed_email,
    send_email_safely,
    verify_email_token,
)

router = APIRouter(prefix="/users", tags=["users"])


def _require_allowed_email(email: str) -> None:
    """Reject addresses outside the configured registration allowlist.

    Enforced at every point a NEW email enters the system (public signup, admin
    creation, email change) — before any message is queued — so a disallowed
    address can never be registered or emailed. This is deliberately a
    write-time policy: an account created under a looser list keeps its
    address (lockout would be worse), so the recovery/resend endpoints do not
    re-check it. An empty allowlist disables the policy entirely.
    """
    if not is_allowed_email(email):
        domains = allowed_email_domains_text()
        detail = (
            f"暂不支持该邮箱域名，当前仅支持：{domains}"
            if domains
            else "暂不支持该邮箱域名"
        )
        raise HTTPException(status_code=400, detail=detail)


def _tombstone_released_email(session: Session, user_id: uuid.UUID, email: str) -> None:
    """Carry the account's usage onto a canonical identity it is releasing.

    An email change frees the OLD address for re-registration; without a
    tombstone the freed mailbox could mint a fresh free allowance ("change
    email → re-register the old address", no deletion needed). Mirrors the
    deletion path (`save_usage_tombstone`), keyed by canonical email, and is a
    no-op when the account has no usage yet.
    """
    usage = session.exec(select(UserUsage).where(UserUsage.user_id == user_id)).first()
    save_usage_tombstone(session=session, emails=[email], usage=usage)


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
    _require_allowed_email(user_in.email)

    user = crud.create_user(session=session, user_create=user_in)
    # An admin creates an account for a known person (they receive the
    # credentials email), so it is trusted from the start — unlike public
    # self-signup, which must confirm the address.
    user.is_email_verified = True
    session.add(user)
    session.commit()
    session.refresh(user)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user.email,
            username=user.email,
            # Bind the welcome reset token to the account's password-change
            # clock so it dies as soon as the new password is set (single-use).
            password_changed_at=user.password_changed_at,
        )
        # The account row is already committed above; an SMTP failure must not
        # 500 the endpoint (the admin would retry into "already exists"). The
        # recipient can always use the reset-password flow instead.
        send_email_safely(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
            text_content=email_data.text_content,
        )
    return user


@router.patch(
    "/me",
    response_model=UserPublic,
    dependencies=[Depends(rate_limit(limit=30, window=60))],
)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user. Changing the email requires the current password and marks
    the account unverified until the new address is confirmed.
    """
    user_data = user_in.model_dump(exclude_unset=True)
    # `current_password` is an authorization proof for email changes, not a
    # column on the user row — never let it reach sqlmodel_update.
    provided_password = user_data.pop("current_password", None)
    if "email" in user_data and user_data["email"] is None:
        raise HTTPException(status_code=422, detail="邮箱不能为空")

    email_changed = "email" in user_data and user_data["email"] != current_user.email
    if email_changed:
        _require_allowed_email(user_data["email"])
        # Verify the current password first (an anti-enumeration ordering).
        if not provided_password:
            raise HTTPException(status_code=422, detail="修改邮箱需要验证当前密码")
        verified, _ = verify_password(provided_password, current_user.hashed_password)
        if not verified:
            raise HTTPException(status_code=400, detail="当前密码错误")
        if settings.emails_enabled:
            # The change is STAGED, not applied: the email only moves once the
            # NEW address verifies (see verify_email). This closes the
            # account-enumeration/email-squatting oracle — a PATCH returns the
            # same result whether or not the target is taken, because no
            # existence check happens here and the response never confirms an
            # immediate change.
            current_user.pending_email = user_data["email"].lower()
            current_user.is_email_verified = False
            # Remove email so sqlmodel_update does not apply it yet; history and
            # email_canonical are updated only when the change is verified.
            user_data.pop("email")
        else:
            # No mail backend: there is nothing that could verify a staged
            # change, so apply it immediately (matching how signup auto-verifies).
            new_email = user_data["email"].lower()
            # The OLD address is released by this change; carry the account's
            # usage onto it so re-registering it cannot refresh the allowance.
            _tombstone_released_email(session, current_user.id, current_user.email)
            current_user.email = new_email
            current_user.email_canonical = canonical_email(new_email)
            history = list(current_user.email_history or [])
            canonical = canonical_email(new_email)
            if canonical not in history:
                history.append(canonical)
            current_user.email_history = history
            user_data.pop("email")

    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent request claimed the target email between the check and
        # this commit (or the address collides with a legacy mixed-case row).
        session.rollback()
        raise HTTPException(status_code=422, detail="无法修改为指定邮箱")
    session.refresh(current_user)

    if email_changed and settings.emails_enabled and current_user.pending_email:
        # The verification link goes to the NEW (pending) address and is BOUND
        # to this staging account (current email in the token), so a link can
        # only apply the change to the account that staged it — even if another
        # account staged the same target first.
        bound_token = generate_email_change_token(
            pending_email=current_user.pending_email,
            current_email=current_user.email,
            password_changed_at=current_user.password_changed_at,
        )
        email_data = generate_verify_email_email(
            email_to=current_user.pending_email, token=bound_token
        )
        if recipient_send_cooldown(current_user.pending_email):
            send_email_safely(
                email_to=current_user.pending_email,
                subject=email_data.subject,
                html_content=email_data.html_content,
                text_content=email_data.text_content,
            )
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
    # Rotating the password revokes every previously issued access token.
    current_user.password_changed_at = get_datetime_utc()
    # A staged email-change link is also a takeover path: if an attacker already
    # pointed pending_email at their inbox, rotation must cancel that change.
    current_user.pending_email = None
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
    # Carry the free-allowance counters onto EVERY canonical email this account
    # has used (incl. addresses it changed away from), so deleting and
    # re-registering any of them cannot refresh the monthly allowance.
    usage = session.exec(
        select(UserUsage).where(UserUsage.user_id == current_user.id)
    ).first()
    history = list(current_user.email_history or []) or [
        canonical_email(current_user.email)
    ]
    save_usage_tombstone(session=session, emails=history, usage=usage)
    # Unlink uploaded files before the DB rows cascade away, so deleting an
    # account leaves no residue on the uploads volume.
    delete_owner_upload_files(session=session, owner_id=current_user.id)
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
        chat_api_format=settings_row.chat_api_format,
        embedding_base_url=settings_row.embedding_base_url,
        embedding_api_key=masked("embedding_api_key"),
        embedding_model=settings_row.embedding_model,
        embedding_api_format=settings_row.embedding_api_format,
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
        "chat_api_format",
        "embedding_api_format",
    ):
        if field in data and not data[field]:
            data[field] = None
    for field in ("chat_api_format", "embedding_api_format"):
        if field in data and data[field] not in {"openai", "openai_v1"}:
            raise HTTPException(
                status_code=422,
                detail="API 格式仅支持 openai 或 openai_v1",
            )
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
        raise HTTPException(status_code=429, detail=_cooldown_detail(cooldown_until))
    if settings_row is not None:
        session.delete(settings_row)
        session.commit()
    return Message(message="已清除模型配置")


def _fetch_models_payload(root: str, api_key: str) -> object:
    response = pinned_request(
        "GET",
        f"{root}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


@router.post(
    "/me/provider-settings/models",
    response_model=list[ModelInfoPublic],
    # This probe spends the server's own chat key (or the caller's) on a live
    # request — rate-limit it like an auth endpoint.
    dependencies=[Depends(rate_limit(limit=10, window=60))],
)
def fetch_available_models(
    body: ModelFetchRequest,
    session: SessionDep,
    current_user: CurrentUser,
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
        # The form masks stored keys, so an empty key here may just mean "use
        # the one I saved" — fall back to it. Never send the *server's* key to
        # an endpoint the user controls.
        stored = load_user_provider_settings(session, current_user.id)
        if stored and stored.chat_api_key:
            user_key = decrypt_secret(stored.chat_api_key) or ""
        if not user_key:
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
    root = resolve_api_base(base_url, body.api_format)
    # When the base URL has no version path, the service may still serve the
    # OpenAI API under /v1 (common for aggregator gateways) — probe it.
    fallback_root: str | None = resolve_api_base(base_url, "openai_v1")
    if body.api_format == "openai_v1" or fallback_root == root:
        fallback_root = None

    def fetch_models() -> list[str]:
        try:
            payload = _fetch_models_payload(root, api_key)
        except (httpx.HTTPError, ValueError, TypeError) as error:
            if fallback_root is None:
                raise HTTPException(
                    status_code=503,
                    detail="无法获取模型，请检查 Base URL 与 API Key 是否正确",
                ) from error
            try:
                payload = _fetch_models_payload(fallback_root, api_key)
            except (httpx.HTTPError, ValueError, TypeError) as fallback_error:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "无法获取模型。若 Base URL 是根域名（如 https://host），"
                        "请在“API 格式”中选择“根域名，自动加 /v1”后重试。"
                    ),
                ) from fallback_error
        data = payload.get("data", []) if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise HTTPException(status_code=502, detail="模型提供方返回了异常数据")
        # Bind the extracted id to a variable so the isinstance() narrows it —
        # ty does not narrow a repeated `item.get("id")` call expression.
        model_ids = [
            model_id
            for item in data
            if isinstance(item, dict)
            for model_id in [item.get("id")]
            if isinstance(model_id, str)
        ][:100]
        if not model_ids:
            raise HTTPException(status_code=502, detail="模型提供方未返回任何模型")
        return model_ids

    if user_key:
        model_ids = fetch_models()
    else:
        # A server-billed probe reserves a bounded amount and keeps a nominal
        # cost on success. The context refunds the full reservation on errors.
        user_settings = load_user_provider_settings(session, current_user.id)
        try:
            with usage_reservation(
                session=session,
                user_id=current_user.id,
                user_settings=user_settings,
                chat_tokens=500,
                chat_source="server",
            ) as reservation:
                model_ids = fetch_models()
                reservation.set_actual(chat_tokens=100)
        except QuotaError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error
    return [ModelInfoPublic(id=model_id) for model_id in model_ids]


@router.post(
    "/signup",
    response_model=SignupResult,
    dependencies=[
        Depends(rate_limit(limit=5, window=60)),
        Depends(require_turnstile),
    ],
)
def register_user(session: SessionDep, user_in: UserRegister) -> SignupResult:
    """
    Create new user without the need to be logged in.

    Registration is domain-allowlisted: `_require_allowed_email` rejects
    addresses outside `ALLOWED_EMAIL_DOMAINS` up front, so a disallowed domain
    never reaches the create/send branches (and no message can be aimed at an
    arbitrary inbox).

    Anti-enumeration: a new signup and an existing account return the *exact
    same* body (no account id/timestamps, and `is_email_verified` only reflects
    whether the mail backend is configured). The exists-branch also runs a
    password hash so the response timing does not reveal whether the account
    existed, and to make probing expensive.
    """
    email = user_in.email
    _require_allowed_email(email)
    exists = crud.get_user_by_email(session=session, email=email) is not None
    if not exists:
        user_create = UserCreate.model_validate(user_in)
        try:
            user = crud.create_user(session=session, user_create=user_create)
        except IntegrityError:
            # Two concurrent signups for the same address raced past the check
            # above; the unique index is authoritative.
            session.rollback()
            exists = True
        else:
            # A deleted account's usage tombstone (if any) is restored so the
            # monthly allowance does not refresh by deleting + re-registering
            # the same address. ensure_period rolls it over if it is old.
            restore_tombstone_usage(session=session, user_id=user.id, email=email)
            session.commit()
            if settings.emails_enabled:
                email_data = generate_verify_email_email(email_to=user.email)
                if recipient_send_cooldown(user.email):
                    send_email_safely(
                        email_to=user.email,
                        subject=email_data.subject,
                        html_content=email_data.html_content,
                        text_content=email_data.text_content,
                    )
            else:
                # No mail backend configured: there is nothing to confirm, so
                # the account is usable immediately (local development /
                # email-disabled self-host).
                user.is_email_verified = True
                session.add(user)
                session.commit()
    else:
        # Equalize timing with the create path (argon2 is slow) and make
        # enumeration attempts expensive.
        get_password_hash(user_in.password)
        if settings.emails_enabled:
            # Re-send the verification link — genuinely useful for an existing
            # unverified account, harmless for a verified one (idempotent), and
            # throttled by the per-recipient cooldown.
            email_data = generate_verify_email_email(email_to=email)
            if recipient_send_cooldown(email):
                send_email_safely(
                    email_to=email,
                    subject=email_data.subject,
                    html_content=email_data.html_content,
                    text_content=email_data.text_content,
                )
    return SignupResult(email=email, is_email_verified=not settings.emails_enabled)


@router.post(
    "/verify-email",
    response_model=Message,
    dependencies=[Depends(rate_limit(limit=10, window=60))],
)
def verify_email(session: SessionDep, body: VerifyEmailRequest) -> Any:
    """
    Confirm email ownership with the signed link token. The endpoint is
    idempotent and reveals nothing beyond "invalid or expired" whether the token
    is malformed, expired, or refers to a removed account. If the token matches
    a STAGED email change (pending_email), the change is applied here.
    """
    email = verify_email_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="验证链接无效或已过期")
    email = email.strip().lower()
    # A staged email change's link is bound to the staging account's CURRENT
    # email; resolve THAT account so a token can never be applied to another
    # account that happens to have staged the same target.
    staging_account_email = email_change_token_account(body.token)
    if staging_account_email is not None:
        user = crud.get_user_by_email(session=session, email=staging_account_email)
        if user is None or not (user.pending_email or "").lower() == email:
            raise HTTPException(status_code=400, detail="验证链接无效或已过期")
        token_pwd = email_change_token_password_changed_at(body.token)
        if user.password_changed_at is not None and (
            token_pwd is None
            or int(user.password_changed_at.timestamp() * 1_000_000) > token_pwd
        ):
            raise HTTPException(status_code=400, detail="验证链接无效或已过期")
    else:
        # A plain (cur-less) token is a SIGNUP verification only: resolve the
        # account by its CURRENT email. A staged email change can ONLY be
        # applied via a cur-bound token — an unbound token must never resolve a
        # pending_email (that fallback is how a collision hijacks the change).
        user = crud.get_user_by_email(session=session, email=email)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="验证链接无效或已过期")

    if user.pending_email and user.pending_email.lower() == email:
        # Apply the staged email change. One live account per canonical mailbox
        # is re-checked here (a variant of the target may have been registered
        # since the change was staged); a conflict silently clears the pending
        # change with the generic error.
        new_canonical = canonical_email(email)
        conflict = session.exec(
            select(User).where(
                User.email_canonical == new_canonical, User.id != user.id
            )
        ).first()
        if conflict:
            user.pending_email = None
            session.add(user)
            session.commit()
            raise HTTPException(status_code=400, detail="验证链接无效或已过期")
        # The OLD address is released by this change; carry the account's usage
        # onto it so re-registering it cannot refresh the allowance.
        _tombstone_released_email(session, user.id, user.email)
        user.email = email
        user.email_canonical = new_canonical
        history = list(user.email_history or [])
        if new_canonical not in history:
            history.append(new_canonical)
        user.email_history = history
        user.pending_email = None
        user.is_email_verified = True
    elif not user.is_email_verified:
        user.is_email_verified = True
    session.add(user)
    session.commit()
    return Message(message="邮箱验证成功")


@router.post(
    "/resend-verification",
    response_model=Message,
    dependencies=[Depends(rate_limit(limit=3, window=300))],
)
def resend_verification(session: SessionDep, body: ResendVerificationRequest) -> Any:
    """
    Re-send the verification email to a given address. The response is generic
    so this endpoint cannot be used to enumerate registered emails.
    """
    user = crud.get_user_by_email(session=session, email=body.email)
    if settings.emails_enabled and user and not user.is_email_verified:
        email_data = generate_verify_email_email(email_to=user.email)
        if recipient_send_cooldown(user.email):
            send_email_safely(
                email_to=user.email,
                subject=email_data.subject,
                html_content=email_data.html_content,
                text_content=email_data.text_content,
            )
    return Message(message="如果该邮箱已注册，我们已发送验证邮件")


@router.post(
    "/me/resend-verification",
    response_model=Message,
    dependencies=[Depends(rate_limit(limit=3, window=300))],
)
def resend_verification_me(current_user: CurrentUser) -> Any:
    """
    Re-send the verification email to the signed-in user (used by the reminder
    banner in the app, so no address has to be typed).
    """
    # A staged email change takes priority: the pending address needs its
    # verification link re-sent, BOUND to this staging account (same as the
    # initial staging in update_user_me) so a resent link can never apply the
    # change to a different account that staged the same target.
    target = current_user.pending_email or current_user.email
    if current_user.is_email_verified and not current_user.pending_email:
        return Message(message="邮箱已验证")
    if settings.emails_enabled:
        token = (
            generate_email_change_token(
                pending_email=current_user.pending_email,
                current_email=current_user.email,
                password_changed_at=current_user.password_changed_at,
            )
            if current_user.pending_email
            else None
        )
        email_data = generate_verify_email_email(email_to=target, token=token)
        if recipient_send_cooldown(target):
            send_email_safely(
                email_to=target,
                subject=email_data.subject,
                html_content=email_data.html_content,
                text_content=email_data.text_content,
            )
    return Message(message="验证邮件已发送")


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
        _require_allowed_email(user_in.email)
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(status_code=409, detail="该邮箱的用户已存在")

    try:
        db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    except IntegrityError:
        # The canonical mailbox identity is already held by another account
        # (e.g. a subaddress/case variant of the target email).
        session.rollback()
        raise HTTPException(status_code=409, detail="该邮箱的用户已存在")
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
    # Carry the free-allowance counters onto every canonical email the account
    # has used before the usage row cascades away (anti-allowance-farming).
    usage = session.exec(select(UserUsage).where(UserUsage.user_id == user_id)).first()
    history = list(user.email_history or []) or [canonical_email(user.email)]
    save_usage_tombstone(session=session, emails=history, usage=usage)
    # Unlink uploaded files before the notebook rows cascade away. The
    # self-service DELETE /users/me path does the same; skipping it here left
    # PDFs/TXT on the uploads volume after an admin deletion.
    delete_owner_upload_files(session=session, owner_id=user.id)
    # Notebooks/sources/conversations cascade via their foreign keys.
    session.delete(user)
    session.commit()
    return Message(message="用户删除成功")
