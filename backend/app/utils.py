import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import emails
import jwt
from jinja2 import Environment, select_autoescape
from jwt.exceptions import InvalidTokenError

from app.core import security
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Render user-supplied values (email addresses, names) HTML-escaped. The email
# field is EmailStr-validated, but autoescape is cheap defense in depth.
_jinja_env = Environment(
    loader=None,
    autoescape=select_autoescape(["html", "xml"]),
)


def _brand_host() -> str:
    """Host part of FRONTEND_HOST (no scheme) for the footer anti-phishing line."""
    try:
        host = urlparse(settings.FRONTEND_HOST).netloc
    except ValueError:
        host = ""
    return host or settings.FRONTEND_HOST


@dataclass
class EmailData:
    html_content: str
    subject: str
    # Plain-text twin of the message. Clients that refuse or render HTML badly
    # fall back to this; its absence is a classic junk-mail signal.
    text_content: str | None = None


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    template_str = (
        Path(__file__).parent / "email-templates" / "build" / template_name
    ).read_text()
    html_content = _jinja_env.from_string(template_str).render(context)
    return html_content


def send_email(
    *,
    email_to: str,
    subject: str = "",
    html_content: str = "",
    text_content: str | None = None,
) -> bool:
    """Send a message and report whether the server accepted it.

    The `emails` library swallows connection/auth failures into the response
    object by default, so a `False` here is the only reliable signal an operator
    gets that a message never went out.
    """
    assert settings.emails_enabled, "no provided configuration for email variables"
    assert settings.EMAILS_FROM_EMAIL  # For type checker
    message = emails.message.Message(
        subject=subject,
        html=html_content,
        text=text_content,
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
    status = getattr(response, "status_code", None)
    if status is None or status == 0 or status >= 400:
        logger.error("Failed to send email to %s: %s", email_to, response)
        return False
    logger.info("send email result: %s", response)
    return True


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - 重置密码"
    # The token rides in the URL *fragment* (`#token=...`), never in the query
    # string: fragments are not sent to the server, not logged by the proxy,
    # and not leaked through the Referer header, so a 48h password-reset JWT
    # cannot be harvested from access logs, browser history sync, or referrers.
    link = f"{settings.FRONTEND_HOST}/reset-password#token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
            "brand_host": _brand_host(),
        },
    )
    text_content = (
        f"{project_name} 重置密码\n\n"
        f"你好 {email}：\n\n"
        f"我们收到了重置密码的请求。点击以下链接设置新密码"
        f"（{settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS} 小时内有效）：\n\n"
        f"{link}\n\n"
        f"如果链接无法点击，请将以上地址复制到浏览器打开。\n\n"
        f"如果你没有请求重置密码，请忽略这封邮件。\n"
    )
    return EmailData(html_content=html_content, subject=subject, text_content=text_content)


def generate_new_account_email(
    email_to: str, username: str, password_changed_at: datetime | None = None
) -> EmailData:
    """Welcome email for admin-created accounts.

    The admin supplies a password to create the row, but that plaintext is
    never emailed back out — the recipient instead receives a one-time
    password-reset link to set a password only they know. A reset token
    expires (unlike a password) and becomes useless after first use.
    """
    project_name = settings.PROJECT_NAME
    subject = f"设置你的初始密码 - {project_name}"
    token = generate_password_reset_token(email_to, password_changed_at)
    # URL fragment (see generate_reset_password_email): the token never
    # reaches the server, logs, or Referer.
    link = f"{settings.FRONTEND_HOST}/reset-password#token={token}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
            "brand_host": _brand_host(),
        },
    )
    text_content = (
        f"{project_name} 新账号\n\n"
        f"你好 {username}：\n\n"
        f"管理员已为你创建 {project_name} 账号。点击以下链接设置一个属于你自己的密码"
        f"（{settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS} 小时内有效）：\n\n"
        f"{link}\n\n"
        f"如果链接无法点击，请将以上地址复制到浏览器打开。\n\n"
        f"设置完成后即可用 {username} 登录 {project_name}。\n\n"
        f"如果你没有请求创建账号，请忽略并删除这封邮件。\n"
    )
    return EmailData(html_content=html_content, subject=subject, text_content=text_content)


def _encode_purpose_token(
    email: str,
    purpose: str,
    hours: int,
    password_changed_at: datetime | None = None,
) -> str:
    delta = timedelta(hours=hours)
    now = datetime.now(UTC)
    expires = now + delta
    claims = {"exp": expires.timestamp(), "nbf": now, "sub": email, "purpose": purpose}
    if password_changed_at is not None:
        # Snapshot of the account's password_changed_at (microsecond
        # precision). A reset token is only usable while that value is
        # unchanged, so a successful reset (or any password change) invalidates
        # outstanding reset tokens immediately.
        claims["pwd"] = int(password_changed_at.timestamp() * 1_000_000)
    encoded_jwt = jwt.encode(
        claims,
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


def generate_password_reset_token(
    email: str, password_changed_at: datetime | None = None
) -> str:
    return _encode_purpose_token(
        email,
        "password_reset",
        settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
        password_changed_at,
    )


def verify_password_reset_token(token: str) -> str | None:
    return _decode_purpose_token(token, "password_reset")


def reset_token_password_changed_at(token: str) -> int | None:
    """The `pwd` snapshot bound to a reset token, or None (unbound/legacy)."""
    try:
        decoded = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
    except InvalidTokenError:
        return None
    if decoded.get("purpose") != "password_reset":
        return None
    pwd = decoded.get("pwd")
    return int(pwd) if isinstance(pwd, (int, float)) else None


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
    # URL fragment (see generate_reset_password_email): the verify JWT never
    # reaches the server, logs, or Referer.
    link = (
        f"{settings.FRONTEND_HOST}/verify-email"
        f"#token={generate_verify_email_token(email_to)}"
    )
    subject = f"验证你的邮箱 - {settings.PROJECT_NAME}"
    html_content = render_email_template(
        template_name="verify_email.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "email": email_to,
            "valid_hours": settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS,
            "link": link,
            "brand_host": _brand_host(),
        },
    )
    text_content = (
        f"{settings.PROJECT_NAME} 邮箱验证\n\n"
        f"你好，欢迎使用 {settings.PROJECT_NAME}！\n\n"
        f"请确认 {email_to} 属于你本人，点击以下链接完成验证"
        f"（{settings.EMAIL_VERIFY_TOKEN_EXPIRE_HOURS} 小时内有效）：\n\n"
        f"{link}\n\n"
        f"如果链接无法点击，请将以上地址复制到浏览器打开。\n\n"
        f"如果你没有注册 {settings.PROJECT_NAME}，请忽略这封邮件，你的邮箱不会发生任何变更。\n"
    )
    return EmailData(html_content=html_content, subject=subject, text_content=text_content)


def send_email_safely(
    *, email_to: str, subject: str, html_content: str, text_content: str | None = None
) -> bool:
    """Send an email without propagating SMTP failures to the caller.

    Registration/verification must succeed even when the mail backend is
    temporarily down; the recipient can always request a new link. Failures are
    logged so operators can investigate. Returns whether the message was
    accepted by the server.
    """
    try:
        return send_email(
            email_to=email_to,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
    except Exception:  # noqa: BLE001 - the mail backend failure must not 500 an API call
        logger.exception(
            "Failed to send email to %s (subject: %s)", email_to, subject
        )
        return False


def canonical_email(email: str) -> str:
    """Canonical mailbox identity used for allowance/anti-farming keys.

    Mailbox delivery is case-insensitive; ``+tag`` subaddressing is broadly
    supported (Gmail, Outlook/Hotmail/Live, iCloud, ProtonMail, Fastmail, Zoho,
    Google-Workspace domains, and most modern providers deliver to the same
    inbox), Gmail additionally ignores dots in the local part, and Googlemail /
    Hotmail / Live are aliases of Gmail / Outlook. Normalizing all of these —
    provider-agnostically, not a hardcoded list — is what makes the
    one-live-account-per-mailbox and allowance-tombstone guarantees hold for
    ANY domain an operator allows (including a `*` allowlist).
    """
    local, sep, domain = email.rpartition("@")
    if not sep:
        return email.strip().lower()
    domain = domain.strip().lower()
    # Cross-domain aliases that deliver to the same physical mailbox.
    if domain == "googlemail.com":
        domain = "gmail.com"
    if domain in {"hotmail.com", "live.com", "msn.com"}:
        domain = "outlook.com"
    # Strip +tag subaddressing for ALL domains. Tradeoff: a provider that
    # treats `+tag` as a literal distinct mailbox would be over-collapsed —
    # acceptable, since subaddressing collapse is the anti-farming default and
    # the operators can read this caveat.
    local = local.split("+", 1)[0]
    if domain == "gmail.com":
        # Gmail ignores dots in the local part.
        local = local.replace(".", "")
    return f"{local.lower()}@{domain}"


def is_allowed_email(email: str) -> bool:
    """Whether `email`'s domain is in the configured signup allowlist.

    A literal `*` entry (or an empty list) disables the restriction — every
    address passes. Comparison is on the exact domain after lowercasing —
    subdomains, prefix-suffix lookalikes and `@qq.com@evil.com` tricks never
    match.
    """
    allowed = {
        d.strip().lower() for d in settings.ALLOWED_EMAIL_DOMAINS if d.strip()
    }
    if not allowed or "*" in allowed:
        return True
    try:
        domain = email.rsplit("@", 1)[1]
    except IndexError:
        return False
    return domain.strip().lower() in allowed


def allowed_email_domains_text() -> str:
    """Comma-joined allowed domains for user-facing error messages."""
    domains = [
        d.strip().lower()
        for d in settings.ALLOWED_EMAIL_DOMAINS
        if d.strip() and d.strip().lower() != "*"
    ]
    return "、".join(domains)
