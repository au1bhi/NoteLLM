from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.core import security
from app.core.config import settings
from app.core.rate_limit import rate_limit, recipient_send_cooldown
from app.models import (
    Message,
    NewPassword,
    Token,
    UserPublic,
    UserUpdate,
    get_datetime_utc,
)
from app.utils import (
    generate_password_reset_token,
    generate_reset_password_email,
    reset_token_password_changed_at,
    send_email_safely,
    verify_password_reset_token,
)

router = APIRouter(tags=["login"])


@router.post(
    "/login/access-token",
    dependencies=[Depends(rate_limit(limit=20, window=60))],
)
def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="邮箱或密码错误")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="用户已停用")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            user.id,
            expires_delta=access_token_expires,
            password_changed_at=user.password_changed_at,
        )
    )


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


@router.post(
    "/password-recovery/{email}",
    dependencies=[Depends(rate_limit(limit=5, window=60))],
)
def recover_password(email: str, session: SessionDep) -> Message:
    """
    Password Recovery
    """
    # Emails are stored lowercase; the path param is a raw string.
    email = email.strip().lower()
    user = crud.get_user_by_email(session=session, email=email)

    if not user or not user.is_active:
        # Uniform 200 for every address: a 404 here is a trivially scriptable
        # account-enumeration oracle (probing is only throttled once the rate
        # limit keys on the endpoint, and the allowlist bounds candidate
        # domains). Equalize timing with the registered branch via the Argon2
        # dummy hash; no email is sent for an unknown address. The per-recipient
        # cooldown still bounds floodable sends to registered inboxes.
        security.verify_password("", crud.DUMMY_HASH)
        return Message(message="密码重置链接已发送，请查收")

    password_reset_token = generate_password_reset_token(
        email=email, password_changed_at=user.password_changed_at
    )
    email_data = generate_reset_password_email(
        email_to=user.email, email=email, token=password_reset_token
    )
    # Never propagate SMTP failures to the client (they would both 500 the
    # endpoint and turn it into an account enumerator). The per-recipient
    # cooldown stops a distributed caller flooding one registered inbox with
    # reset links; like every other send path, a cooldown hit is silently
    # skipped and the generic success response is still returned.
    if recipient_send_cooldown(email):
        send_email_safely(
            email_to=user.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
            text_content=email_data.text_content,
        )
    return Message(message="密码重置链接已发送，请查收")


@router.post(
    "/reset-password/",
    dependencies=[Depends(rate_limit(limit=10, window=60))],
)
def reset_password(session: SessionDep, body: NewPassword) -> Message:
    """
    Reset password
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="无效的令牌")
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        # Don't reveal that the user doesn't exist - use same error as invalid token
        raise HTTPException(status_code=400, detail="无效的令牌")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="用户已停用")
    # A reset token is single-use: any password change (including a prior
    # successful reset) bumps password_changed_at beyond the token's snapshot,
    # so replayed links are rejected instead of re-resetting the account. The
    # check is unconditional: a token issued without a `pwd` snapshot (legacy
    # or welcome-email tokens before the fix) is itself replayable, so once an
    # account has a password-change clock it is rejected outright.
    token_pwd = reset_token_password_changed_at(body.token)
    if user.password_changed_at is not None and (
        token_pwd is None
        or int(user.password_changed_at.timestamp() * 1_000_000) > token_pwd
    ):
        raise HTTPException(status_code=400, detail="无效的令牌")
    user_in_update = UserUpdate(password=body.new_password)
    crud.update_user(
        session=session,
        db_user=user,
        user_in=user_in_update,
    )
    user.password_changed_at = get_datetime_utc()
    session.add(user)
    session.commit()
    return Message(message="密码更新成功")


@router.post(
    "/password-recovery-html-content/{email}",
    dependencies=[Depends(get_current_active_superuser)],
    response_class=HTMLResponse,
)
def recover_password_html_content(email: str, session: SessionDep) -> Any:
    """
    HTML Content for Password Recovery
    """
    user = crud.get_user_by_email(session=session, email=email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="系统中不存在该用户名的用户。",
        )
    password_reset_token = generate_password_reset_token(
        email=email, password_changed_at=user.password_changed_at
    )
    email_data = generate_reset_password_email(
        email_to=user.email, email=email, token=password_reset_token
    )

    return HTMLResponse(
        content=email_data.html_content, headers={"subject:": email_data.subject}
    )
