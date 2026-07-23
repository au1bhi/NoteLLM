import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from pydantic import EmailStr
from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel

from app.core.config import settings


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


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


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)
    notebooks: list[Notebook] = Relationship(
        back_populates="owner", cascade_delete=True
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


class NotebookBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class NotebookCreate(NotebookBase):
    pass


class NotebookUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


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
    sources: list[Source] = Relationship(back_populates="notebook", cascade_delete=True)
    conversations: list[Conversation] = Relationship(
        back_populates="notebook", cascade_delete=True
    )


class NotebookPublic(NotebookBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class NotebooksPublic(SQLModel):
    data: list[NotebookPublic]
    count: int


class SourceBase(SQLModel):
    display_name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(max_length=100)
    file_size_bytes: int = Field(ge=0)


class Source(SourceBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    notebook_id: uuid.UUID = Field(
        foreign_key="notebook.id", nullable=False, ondelete="CASCADE", index=True
    )
    storage_path: str = Field(max_length=1024)
    status: str = Field(default="pending", max_length=32)
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
    chunks: list[Chunk] = Relationship(back_populates="source", cascade_delete=True)


class SourcePublic(SourceBase):
    id: uuid.UUID
    notebook_id: uuid.UUID
    status: str
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


class Conversation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    notebook_id: uuid.UUID = Field(
        foreign_key="notebook.id", nullable=False, ondelete="CASCADE", index=True
    )
    title: str = Field(max_length=255)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    notebook: Notebook | None = Relationship(back_populates="conversations")
    messages: list[ConversationMessage] = Relationship(
        back_populates="conversation", cascade_delete=True
    )


class ConversationPublic(SQLModel):
    id: uuid.UUID
    notebook_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationsPublic(SQLModel):
    data: list[ConversationPublic]
    count: int


class ConversationMessageCreate(SQLModel):
    content: str = Field(min_length=1, max_length=4000)


class ConversationMessage(SQLModel, table=True):
    __tablename__ = "conversation_message"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(
        foreign_key="conversation.id", nullable=False, ondelete="CASCADE", index=True
    )
    role: str = Field(max_length=16)
    content: str
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    conversation: Conversation | None = Relationship(back_populates="messages")
    citations: list[Citation] = Relationship(
        back_populates="message", cascade_delete=True
    )


class Citation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(
        foreign_key="conversation_message.id", nullable=False, ondelete="CASCADE", index=True
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
    role: str
    content: str
    created_at: datetime
    citations: list[CitationPublic]


class ConversationDetailPublic(ConversationPublic):
    messages: list[ConversationMessagePublic]


class Chunk(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    source_id: uuid.UUID = Field(
        foreign_key="source.id", nullable=False, ondelete="CASCADE", index=True
    )
    ordinal: int = Field(ge=0)
    content: str
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


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
