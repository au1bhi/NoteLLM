import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import emails
import jwt
from jinja2 import Template
from jwt.exceptions import InvalidTokenError

from app.core import security
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    html_content = Template(template_str).render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
) -> None:
    assert settings.emails_enabled, "no provided configuration for email variables"
    assert settings.EMAILS_FROM_EMAIL  # For type checker
    message = emails.message.Message(
        subject=subject,
        html=html_content,
        mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
    )
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    logger.info(f"send email result: {response}")


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Password recovery for user {email}"
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(
    email_to: str, username: str, password: str
) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - New account for user {username}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "password": password,
            "email": email_to,
            "link": settings.FRONTEND_HOST,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def _encode_purpose_token(email: str, purpose: str, hours: int) -> str:
    delta = timedelta(hours=hours)
    now = datetime.now(UTC)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email, "purpose": purpose},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def _decode_purpose_token(token: str, purpose: str) -> str | None:
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
    except InvalidTokenError:
        return None
    if decoded_token.get("purpose") != purpose:
        return None
    sub = decoded_token.get("sub")
    return str(sub) if isinstance(sub, str) else None


def generate_password_reset_token(email: str) -> str:
    return _encode_purpose_token(
        email, "password_reset", settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS
    )


def verify_password_reset_token(token: str) -> str | None:
    return _decode_purpose_token(token, "password_reset")


def generate_verify_email_token(email: str) -> str:
    """Signed link token that proves ownership of `email`. Purpose-scoped so a
    password-reset token can never be replayed as a verification token (and
    vice versa)."""
    return _encode_purpose_token(
        email, "email_verify", settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS
    )


def verify_email_token(token: str) -> str | None:
    """Return the email bound to a valid verification token, or None."""
    return _decode_purpose_token(token, "email_verify")


def generate_verify_email_email(email_to: str) -> EmailData:
    link = (
        f"{settings.FRONTEND_HOST}/verify-email"
        f"?token={generate_verify_email_token(email_to)}"
    )
    subject = f"验证你的邮箱 - {settings.PROJECT_NAME}"
    html_content = render_email_template(
        template_name="verify_email.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "email": email_to,
            "valid_hours": settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def send_email_safely(
    *, email_to: str, subject: str, html_content: str
) -> None:
    """Send an email without propagating SMTP failures to the caller.

    Registration/verification must succeed even when the mail backend is
    temporarily down; the recipient can always request a new link. Failures are
    logged so operators can investigate.
    """
    try:
        send_email(
            email_to=email_to, subject=subject, html_content=html_content
        )
    except Exception:  # noqa: BLE001 - the mail backend failure must not 500 an API call
        logger.exception(
            "Failed to send email to %s (subject: %s)", email_to, subject
        )
