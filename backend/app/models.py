import uuid
from datetime import UTC, date, datetime
from typing import Literal

from pgvector.sqlalchemy import Vector
from pydantic import EmailStr, field_validator
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, Relationship, SQLModel

from app.core.config import settings


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_email(value: object) -> object:
    """Lowercase emails on input.

    Mailbox delivery is case-insensitive, but `EmailStr` only lowercases the
    domain part. Storing the local part in its original case lets the same
    mailbox register under case variants and makes login lookups case-sensitive
    — normalize to lowercase so "A@X.com" and "a@x.com" are the same account.
    """
    if isinstance(value, str):
        return value.strip().lower()
    return value


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class SignupResult(SQLModel):
    """Response for public self-signup.

    Deliberately carries no account id or timestamps, and `is_email_verified`
    reflects the mail-backend state (whether verification is required at all),
    never the actual account — so the endpoint cannot be used to enumerate
    registered addresses (a new signup and an existing account return the exact
    same body).
    """

    email: str
    is_email_verified: bool

    @field_validator("email", mode="before")
    @classmethod
    def _email_lower(cls, value: object) -> object:
        return _normalize_email(value)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def _email_lower(cls, value: object) -> object:
        return _normalize_email(value)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    # Required when `email` changes. Changing the login identifier of an account
    # is a sensitive action: it must be authorized by the current password so a
    # stolen session alone cannot hijack the account (e.g. by moving it to an
    # attacker-owned address and then using password recovery).
    current_password: str | None = Field(default=None, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def _email_lower(cls, value: object) -> object:
        return _normalize_email(value)


class VerifyEmailRequest(SQLModel):
    token: str = Field(min_length=1, max_length=2048)


class ResendVerificationRequest(SQLModel):
    email: EmailStr = Field(max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def _email_lower(cls, value: object) -> object:
        return _normalize_email(value)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    # Set whenever the password is created or changed; access and password-reset
    # tokens carry a snapshot of this value so a password change invalidates
    # every previously issued token (stolen JWTs stop working immediately).
    password_changed_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    # False until the user confirms ownership of the email via the link in the
    # verification message. Purely informational: login and the core features
    # stay available, the client shows a reminder banner instead.
    is_email_verified: bool = False
    # Canonical forms of every email this account has used (canonical_email()).
    # Used by the allowance tombstone so deleting an account carries the usage
    # onto ALL its former addresses — otherwise "change email, then delete,
    # then re-register the old address" would reset the monthly free allowance.
    email_history: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Canonical mailbox identity of the CURRENT email, UNIQUE. Two subaddress/
    # dot-variant/case-variant strings that deliver to one inbox share a value,
    # so a physical mailbox can never hold more than one live account (kills
    # concurrent allowance farming). Set in crud.create_user / update paths.
    email_canonical: str = Field(max_length=255, unique=True, index=True)
    # A requested email change is NOT applied immediately: it is staged here and
    # only moves to `email` when the NEW address verifies. This keeps the email
    # change from being an account-enumeration/squatting oracle (a PATCH always
    # returns the same generic result; whether the address is free is only
    # revealed to the person who can verify it).
    pending_email: str | None = Field(default=None, max_length=255)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    notebooks: list["Notebook"] = Relationship(
        back_populates="owner", cascade_delete=True
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None
    is_email_verified: bool = False
    # A staged email change awaiting verification of the new address; the
    # account's `email` stays unchanged until then.
    pending_email: str | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class UserProviderSettingsCreate(SQLModel):
    """Incoming per-user provider settings; empty api_key fields keep the stored key."""

    chat_base_url: str | None = Field(default=None, max_length=1000)
    chat_api_key: str | None = Field(default=None, max_length=1000)
    chat_model: str | None = Field(default=None, max_length=255)
    # API format: "openai" (base URL already contains the version path) or
    # "openai_v1" (root domain, append /v1 automatically). None keeps stored.
    chat_api_format: str | None = Field(default=None, max_length=32)
    embedding_base_url: str | None = Field(default=None, max_length=1000)
    embedding_api_key: str | None = Field(default=None, max_length=1000)
    embedding_model: str | None = Field(default=None, max_length=255)
    embedding_api_format: str | None = Field(default=None, max_length=32)


class UserProviderSettings(UserProviderSettingsCreate, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        ondelete="CASCADE",
        index=True,
        unique=True,
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    # When the user last switched billing between their own key and the
    # server default; drives the switch-back cooldown. None means no switch
    # has happened yet (or they have no own key).
    provider_changed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class UserProviderSettingsPublic(SQLModel):
    """Settings returned to the client; API keys are always masked.

    `cooldown_until` is set when the user has configured their own API key and
    is still inside the switch-back window — clearing the config to revert to
    the server default is blocked until that time.
    """

    chat_base_url: str | None = None
    chat_api_key: str = ""
    chat_model: str | None = None
    chat_api_format: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str = ""
    embedding_model: str | None = None
    embedding_api_format: str | None = None
    cooldown_until: datetime | None = None


class UserUsage(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        ondelete="CASCADE",
        index=True,
        unique=True,
    )
    chat_tokens: int = Field(default=0, ge=0)
    embedding_chars: int = Field(default=0, ge=0)
    # Start of the current allowance period (calendar month). None means the
    # counters have not been attached to a period yet and reset on first use.
    period_start: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class UserUsagePublic(SQLModel):
    """Usage counters plus the free allowance that applies to each dimension.

    `chat_quota`/`embedding_quota` are None when the user brings their own API
    key (unlimited) or when nothing is configured (cannot be used at all).
    `*_source` tells the client who is billed: "server", "user" or "none".
    """

    chat_tokens: int
    chat_quota: int | None = None
    chat_source: Literal["server", "user", "none"] = "none"
    embedding_chars: int
    embedding_quota: int | None = None
    embedding_source: Literal["server", "user", "none"] = "none"
    period_start: datetime | None = None


class EmailUsageTombstone(SQLModel, table=True):
    """Free-allowance usage carried across account deletion, keyed by the
    normalized email.

    `UserUsage` rows cascade away when their user is deleted; without this,
    deleting and re-registering the same address would mint a brand-new monthly
    allowance every time (unbounded free LLM spend for the operator). The
    counters are restored to a re-registered account's usage row so the
    allowance survives deletion.
    """

    email: str = Field(primary_key=True, max_length=255)
    period_start: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    chat_tokens: int = Field(default=0, ge=0)
    embedding_chars: int = Field(default=0, ge=0)
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class ModelFetchRequest(SQLModel):
    """Fetch available model IDs from an OpenAI-compatible /models endpoint.
    Empty base_url/api_key fall back to the server's configured provider.
    `api_format` follows the ProviderConfig convention ("openai" | "openai_v1")."""

    base_url: str = Field(default="", max_length=1000)
    api_key: str = Field(default="", max_length=1000)
    api_format: str = Field(default="openai", max_length=32)


class ModelInfoPublic(SQLModel):
    id: str


# Shared properties
class NotebookBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class NotebookCreate(NotebookBase):
    pass


class NotebookUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    is_pinned: bool | None = None


class Notebook(NotebookBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner: User | None = Relationship(back_populates="notebooks")
    sources: list["Source"] = Relationship(
        back_populates="notebook", cascade_delete=True
    )
    conversations: list["Conversation"] = Relationship(
        back_populates="notebook", cascade_delete=True
    )
    overview: str | None = Field(default=None)
    overview_topics: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    overview_updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    is_pinned: bool = False


class NotebookPublic(NotebookBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    is_pinned: bool = False


class NotebookOverviewPublic(SQLModel):
    summary: str
    topics: list[str]
    updated_at: datetime | None = None


class StudySectionPublic(SQLModel):
    title: str
    content: str


class StudyFaqPublic(SQLModel):
    question: str
    answer: str


class StudyGuidePublic(SQLModel):
    sections: list[StudySectionPublic]
    faqs: list[StudyFaqPublic]


class NotebooksPublic(SQLModel):
    data: list[NotebookPublic]
    count: int


class SourceBase(SQLModel):
    display_name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(max_length=100)
    file_size_bytes: int = Field(ge=0)


SourceStatus = Literal["pending", "processing", "ready", "failed"]


class Source(SourceBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    notebook_id: uuid.UUID = Field(
        foreign_key="notebook.id", nullable=False, ondelete="CASCADE", index=True
    )
    storage_path: str = Field(max_length=1024)
    status: SourceStatus = Field(
        default="pending", sa_column=Column(String(32), nullable=False)
    )
    error_message: str | None = Field(default=None, max_length=1000)
    page_count: int | None = Field(default=None, ge=0)
    char_count: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    processed_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    notebook: Notebook | None = Relationship(back_populates="sources")
    chunks: list["Chunk"] = Relationship(back_populates="source", cascade_delete=True)


class SourcePublic(SourceBase):
    id: uuid.UUID
    notebook_id: uuid.UUID
    status: SourceStatus
    error_message: str | None
    page_count: int | None
    char_count: int | None
    created_at: datetime
    processed_at: datetime | None


class SourcesPublic(SQLModel):
    data: list[SourcePublic]
    count: int


class SearchRequest(SQLModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=10)


class RetrievedChunkPublic(SQLModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_display_name: str
    content: str
    page_number: int | None
    score: float


class RetrievedChunksPublic(SQLModel):
    data: list[RetrievedChunkPublic]


class ConversationCreate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ConversationUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    is_pinned: bool | None = None


class Conversation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    notebook_id: uuid.UUID = Field(
        foreign_key="notebook.id", nullable=False, ondelete="CASCADE", index=True
    )
    title: str = Field(max_length=255)
    is_pinned: bool = False
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    notebook: Notebook | None = Relationship(back_populates="conversations")
    messages: list["ConversationMessage"] = Relationship(
        back_populates="conversation", cascade_delete=True
    )
    study_plans: list["StudyPlan"] = Relationship(
        back_populates="conversation", cascade_delete=True
    )


class ConversationPublic(SQLModel):
    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime


class ConversationsPublic(SQLModel):
    data: list[ConversationPublic]
    count: int


StudyPlanDifficulty = Literal["beginner", "intermediate", "advanced"]


class StudyPlanGenerateRequest(SQLModel):
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class StudyPlanAiAdjustRequest(SQLModel):
    instruction: str = Field(min_length=1, max_length=2000)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)


class StudyPlanUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    reminder_enabled: bool | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class StudyTaskCreate(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    start_date: date
    end_date: date
    estimated_minutes: int = Field(default=45, ge=15, le=480)
    sort_order: int = Field(default=0, ge=0)


class StudyTaskUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    estimated_minutes: int | None = Field(default=None, ge=15, le=480)
    sort_order: int | None = Field(default=None, ge=0)
    is_completed: bool | None = None


class StudyPlan(SQLModel, table=True):
    __tablename__ = "study_plan"
    __table_args__ = (UniqueConstraint("conversation_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversation.id",
        nullable=False,
        ondelete="CASCADE",
        index=True,
    )
    title: str = Field(max_length=255)
    summary: str = Field(sa_column=Column(Text, nullable=False))
    difficulty: str = Field(max_length=16)
    start_date: date
    end_date: date
    timezone: str = Field(default="Asia/Shanghai", max_length=64)
    reminder_enabled: bool = False
    last_reminder_date: date | None = None
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    conversation: Conversation | None = Relationship(back_populates="study_plans")
    tasks: list["StudyTask"] = Relationship(back_populates="plan", cascade_delete=True)


class StudyTask(SQLModel, table=True):
    __tablename__ = "study_task"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plan_id: uuid.UUID = Field(
        foreign_key="study_plan.id",
        nullable=False,
        ondelete="CASCADE",
        index=True,
    )
    title: str = Field(max_length=255)
    description: str = Field(sa_column=Column(Text, nullable=False))
    start_date: date
    end_date: date
    estimated_minutes: int = Field(default=45, ge=15, le=480)
    sort_order: int = Field(default=0, ge=0)
    is_completed: bool = False
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    plan: StudyPlan | None = Relationship(back_populates="tasks")


class StudyTaskPublic(SQLModel):
    id: uuid.UUID
    title: str
    description: str
    start_date: date
    end_date: date
    estimated_minutes: int
    sort_order: int
    is_completed: bool


class StudyPlanPublic(SQLModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    title: str
    summary: str
    difficulty: StudyPlanDifficulty
    start_date: date
    end_date: date
    timezone: str
    reminder_enabled: bool
    reminder_time: str = "09:00"
    email_reminder_available: bool
    created_at: datetime
    updated_at: datetime
    tasks: list[StudyTaskPublic]


class StudyPlanListItem(StudyPlanPublic):
    notebook_id: uuid.UUID
    notebook_title: str
    conversation_title: str


class StudyPlansPublic(SQLModel):
    data: list[StudyPlanListItem]
    count: int


AnswerMode = Literal["grounded", "hybrid", "knowledge"]


class ConversationMessageCreate(SQLModel):
    content: str = Field(min_length=1, max_length=4000)
    mode: AnswerMode = "grounded"
    source_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class ConversationMessage(SQLModel, table=True):
    __tablename__ = "conversation_message"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversation.id", nullable=False, ondelete="CASCADE", index=True
    )
    role: Literal["user", "assistant"] = Field(
        sa_column=Column(String(16), nullable=False)
    )
    content: str = Field(sa_column=Column(Text, nullable=False))
    suggestions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    conversation: Conversation | None = Relationship(back_populates="messages")
    citations: list["Citation"] = Relationship(
        back_populates="message", cascade_delete=True
    )


class Citation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(
        foreign_key="conversation_message.id",
        nullable=False,
        ondelete="CASCADE",
        index=True,
    )
    chunk_id: uuid.UUID = Field(
        foreign_key="chunk.id", nullable=False, ondelete="CASCADE", index=True
    )
    ordinal: int = Field(ge=0)
    quote: str = Field(max_length=500)
    message: ConversationMessage | None = Relationship(back_populates="citations")


class CitationPublic(SQLModel):
    chunk_id: uuid.UUID
    ordinal: int
    quote: str
    source_display_name: str
    page_number: int | None


class ConversationMessagePublic(SQLModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    suggestions: list[str] = []
    citations: list[CitationPublic]


class ConversationDetailPublic(ConversationPublic):
    messages: list[ConversationMessagePublic]


class Chunk(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("source_id", "ordinal", name="uq_chunk_source_ordinal"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_id: uuid.UUID = Field(
        foreign_key="source.id", nullable=False, ondelete="CASCADE", index=True
    )
    ordinal: int = Field(ge=0)
    content: str = Field(sa_column=Column(Text, nullable=False))
    page_number: int | None = Field(default=None, ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(settings.EMBEDDING_DIMENSIONS), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    source: Source | None = Relationship(back_populates="chunks")


# Generic message
class Message(SQLModel):
    message: str


# Public, unauthenticated metadata served to the frontend. Kept minimal on
# purpose — nothing here may depend on a logged-in user.
class WatermarkPublic(SQLModel):
    enabled: bool = True
    text: str


class TurnstilePublic(SQLModel):
    enabled: bool = False
    site_key: str | None = None


class RateLimitBucket(SQLModel, table=True):
    __tablename__ = "rate_limit_bucket"

    key: str = Field(primary_key=True, max_length=64)
    count: int = Field(default=0, ge=0)
    window_started_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore
    updated_at: datetime = Field(index=True, sa_type=DateTime(timezone=True))  # type: ignore


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None
    # Epoch of the user's password_changed_at at token-issue time; used to
    # reject JWTs that predate a password change.
    pwd: int | None = None


class NewPassword(SQLModel):
    token: str = Field(min_length=1, max_length=2048)
    new_password: str = Field(min_length=8, max_length=128)
