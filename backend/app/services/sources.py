import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from fastapi import HTTPException, UploadFile, status
from sqlmodel import Session, col, delete, func, select

from app.core.config import settings
from app.core.db import engine
from app.models import Chunk, Notebook, Source, get_datetime_utc
from app.services.embeddings import EmbeddingError, get_embedding_provider
from app.services.provider_settings import (
    effective_embedding_config,
    load_user_provider_settings,
)
from app.services.usage import QuotaError, reserve_usage, settle_usage

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
CHUNK_MIN_BREAK = 500
UPLOAD_CHUNK_SIZE = 64 * 1024
EMBEDDING_BATCH_SIZE = 64

SUPPORTED_EXTENSIONS = {
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}

# PDF extraction bounds: a 10 MiB upload can be a FlateDecode decompression
# bomb (multi-GB of rendered text) or declare tens of thousands of cheap pages,
# tying up a worker and unbounded memory in PyMuPDF. Cap both so extraction
# cost stays bounded regardless of the quota state (quota is reserved only
# after extraction).
MAX_PDF_PAGES = 500
MAX_EXTRACTED_CHARS = 5_000_000


@dataclass(frozen=True)
class ExtractedPage:
    text: str
    page_number: int | None


@dataclass(frozen=True)
class ChunkData:
    char_end: int
    char_start: int
    content: str
    page_number: int | None


def get_upload_path(source: Source) -> Path:
    return settings.UPLOADS_DIR / str(source.notebook_id) / source.storage_path


def validate_upload(upload: UploadFile) -> tuple[str, str]:
    if not upload.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(upload.filename).suffix.lower()
    media_type = SUPPORTED_EXTENSIONS.get(suffix)
    if not media_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 PDF、TXT 和 Markdown 文件",
        )
    accepted_content_types = {"", "application/octet-stream", media_type}
    if suffix == ".md":
        accepted_content_types.add("text/plain")
    if upload.content_type not in accepted_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="文件内容类型与扩展名不匹配",
        )
    return suffix, media_type


async def save_upload(upload: UploadFile, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with destination.open("wb") as output:
            while content := await upload.read(UPLOAD_CHUNK_SIZE):
                size += len(content)
                if size > settings.MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"文件大小不能超过 {settings.MAX_UPLOAD_SIZE_BYTES // 1024 // 1024} MiB",
                    )
                output.write(content)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return size


def extract_pages(path: Path, media_type: str) -> list[ExtractedPage]:
    if media_type in {"text/plain", "text/markdown"}:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("文本文件必须使用 UTF-8 编码") from error
        if len(text) > MAX_EXTRACTED_CHARS:
            raise ValueError(
                f"文件提取的文本超过 {MAX_EXTRACTED_CHARS} 字符上限，无法处理"
            )
        return [ExtractedPage(text=text, page_number=None)]

    try:
        document = fitz.open(path)
    except fitz.FileDataError as error:
        raise ValueError("无法打开该 PDF") from error

    if document.page_count > MAX_PDF_PAGES:
        document.close()
        raise ValueError(f"PDF 页数超过 {MAX_PDF_PAGES} 页上限，无法处理")

    try:
        pages: list[ExtractedPage] = []
        total_chars = 0
        for index in range(document.page_count):
            page_text = document.load_page(index).get_text("text")
            total_chars += len(page_text)
            if total_chars > MAX_EXTRACTED_CHARS:
                raise ValueError(
                    f"PDF 提取的文本超过 {MAX_EXTRACTED_CHARS} 字符上限，无法处理"
                )
            pages.append(
                ExtractedPage(text=page_text, page_number=index + 1)
            )
    finally:
        document.close()
    return pages


def split_page(page: ExtractedPage) -> Iterable[ChunkData]:
    text = page.text.strip()
    if not text:
        return []

    chunks: list[ChunkData] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            break_at = max(
                text.rfind("\n", start + CHUNK_MIN_BREAK, end),
                text.rfind(" ", start + CHUNK_MIN_BREAK, end),
            )
            if break_at > start:
                end = break_at + 1
        content = text[start:end].strip()
        if content:
            chunks.append(
                ChunkData(
                    char_end=end,
                    char_start=start,
                    content=content,
                    page_number=page.page_number,
                )
            )
        if end == len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def process_source(*, session: Session, source: Source) -> None:
    session.exec(delete(Chunk).where(col(Chunk.source_id) == source.id))
    source.status = "processing"
    source.error_message = None
    session.add(source)
    session.commit()

    def mark_failed(message: str) -> None:
        source.status = "failed"
        source.error_message = message[:1000]
        source.processed_at = get_datetime_utc()

    try:
        pages = extract_pages(get_upload_path(source), source.media_type)
        chunks = [chunk for page in pages for chunk in split_page(page)]
        if not chunks:
            raise ValueError("该资料没有可提取的文本")
        notebook = session.get(Notebook, source.notebook_id)
        user_settings = (
            load_user_provider_settings(session, notebook.owner_id)
            if notebook
            else None
        )
        embedded_chars = 0
        if notebook:
            # Reserve the exact embedding char count atomically before calling
            # the provider, so a single oversized upload cannot blow past the
            # monthly allowance and concurrent uploads serialize correctly.
            embedded_chars = sum(len(chunk.content) for chunk in chunks)
            reserve_usage(
                session=session,
                user_id=notebook.owner_id,
                user_settings=user_settings,
                embedding_chars=embedded_chars,
            )
        embedding_provider = get_embedding_provider(
            effective_embedding_config(user_settings)
        )
        embeddings = [
            embedding
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE)
            for embedding in embedding_provider.embed(
                [
                    chunk.content
                    for chunk in chunks[start : start + EMBEDDING_BATCH_SIZE]
                ]
            )
        ]
        for ordinal, chunk in enumerate(chunks):
            session.add(
                Chunk(
                    source_id=source.id,
                    ordinal=ordinal,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    embedding=embeddings[ordinal],
                )
            )
        source.status = "ready"
        source.page_count = (
            len(pages) if source.media_type == "application/pdf" else None
        )
        source.char_count = sum(len(page.text) for page in pages)
        source.processed_at = get_datetime_utc()
    except (
        EmbeddingError,
        OSError,
        ValueError,
        QuotaError,
        fitz.FileDataError,
    ) as error:
        # Refund the embedding reservation when the provider call failed, so a
        # burst of failed uploads cannot drain the monthly allowance.
        if notebook and embedded_chars:
            settle_usage(
                session=session,
                user_id=notebook.owner_id,
                embedding_chars=-embedded_chars,
            )
        mark_failed(str(error))
    except Exception as error:
        # Never leave the source stuck in "processing" on an unexpected error.
        mark_failed(f"Unexpected error: {error}")

    try:
        session.add(source)
        session.commit()
        session.refresh(source)
    except Exception:
        # The commit/refresh failed (e.g. the source was deleted concurrently);
        # roll back cleanly instead of surfacing a 500.
        session.rollback()


async def create_source_from_upload(
    *, session: Session, notebook: Notebook, upload: UploadFile
) -> Source:
    suffix, media_type = validate_upload(upload)
    source = Source(
        notebook_id=notebook.id,
        display_name=Path(upload.filename or "source").name[:255],
        media_type=media_type,
        file_size_bytes=0,
        storage_path=f"{uuid.uuid4()}{suffix}",
    )
    session.add(source)
    session.commit()
    session.refresh(source)

    try:
        source.file_size_bytes = await save_upload(upload, get_upload_path(source))
        session.add(source)
        session.commit()
        # Enforce the per-user storage cap after the size is known; on
        # rejection the file and row are removed below so failed uploads do
        # not accumulate on the uploads volume.
        enforce_user_storage_limit(session=session, owner_id=notebook.owner_id)
        # NOTE: process_source is intentionally NOT called here — the caller
        # offloads the blocking extraction+embedding off the async event loop
        # (run_in_threadpool with process_source_isolated).
    except HTTPException:
        delete_source_file(source)
        session.delete(source)
        session.commit()
        raise
    except OSError as error:
        source.status = "failed"
        source.error_message = str(error)[:1000]
        source.processed_at = get_datetime_utc()
        session.add(source)
        session.commit()
        session.refresh(source)
    return source


def process_source_isolated(source_id: uuid.UUID) -> None:
    """Run process_source in its own session.

    Extraction + embedding are CPU/network heavy and must not block the async
    event loop; call this via run_in_threadpool from async handlers. Its own
    session avoids sharing the request-scoped session across threads.
    """
    with Session(engine) as session:
        source = session.get(Source, source_id)
        if source is None:
            return
        process_source(session=session, source=source)


def delete_source_file(source: Source) -> None:
    source_path = get_upload_path(source)
    source_path.unlink(missing_ok=True)
    parent = source_path.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def user_storage_bytes(*, session: Session, owner_id: uuid.UUID) -> int:
    """Total bytes stored across all of a user's sources (all notebooks)."""
    notebook_ids = select(Notebook.id).where(col(Notebook.owner_id) == owner_id)
    total = session.exec(
        select(func.coalesce(func.sum(Source.file_size_bytes), 0)).where(
            col(Source.notebook_id).in_(notebook_ids)
        )
    ).one()
    return int(total or 0)


def enforce_user_storage_limit(*, session: Session, owner_id: uuid.UUID) -> None:
    """Reject the upload if the user would exceed their total storage quota."""
    if user_storage_bytes(session=session, owner_id=owner_id) > settings.MAX_USER_STORAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"单个用户的总存储不能超过 "
                f"{settings.MAX_USER_STORAGE_BYTES // 1024 // 1024} MiB，请先删除部分资料"
            ),
        )


def delete_notebook_files(notebook_id: uuid.UUID) -> None:
    """Remove the upload directory of a notebook (used when it is deleted)."""
    notebook_dir = settings.UPLOADS_DIR / str(notebook_id)
    if notebook_dir.exists():
        for path in notebook_dir.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
        try:
            notebook_dir.rmdir()
        except OSError:
            pass


def delete_source(*, session: Session, source: Source) -> None:
    delete_source_file(source)
    session.delete(source)
    session.commit()
