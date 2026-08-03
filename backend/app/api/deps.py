import uuid
from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
        # Access tokens carry a UUID subject. Purpose-scoped email tokens
        # (verify/reset) carry an email here; never treat one as a user id.
        if not token_data.sub:
            raise InvalidTokenError("missing sub")
        user_id = uuid.UUID(token_data.sub)
    except (InvalidTokenError, ValidationError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无法验证凭据",
        )
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已停用")
    if user.password_changed_at is not None and (
        # A missing `pwd` snapshot means a legacy token that cannot be checked
        # against the revocation clock — treat it as revoked. (All new access
        # tokens carry `pwd`.) This closes the NULL/legacy-token gap where a
        # password change left old JWTs usable.
        token_data.pwd is None
        or int(user.password_changed_at.timestamp() * 1_000_000) > token_data.pwd
    ):
        # The password was rotated after this token was issued — the token is
        # revoked (a stolen JWT must not survive the owner changing password).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="凭据已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="该用户权限不足")
    return current_user
