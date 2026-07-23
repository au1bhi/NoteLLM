import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from fastapi import HTTPException, UploadFile, status
from sqlmodel import Session, col, delete

from app.core.config import settings
from app.models import Chunk, Notebook, Source, get_datetime_utc
from app.services.embeddings import EmbeddingError, get_embedding_provider

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
        raise HTTPException(status_code=400, detail="A file name is required")

    suffix = Path(upload.filename).suffix.lower()
    media_type = SUPPORTED_EXTENSIONS.get(suffix)
    if not media_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, TXT, and Markdown files are supported",
        )
    accepted_content_types = {"", "application/octet-stream", media_type}
    if suffix == ".md":
        accepted_content_types.add("text/plain")
    if upload.content_type not in accepted_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file content type does not match its extension",
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
                        detail=f"Files must be at most {settings.MAX_UPLOAD_SIZE_BYTES // 1024 // 1024} MiB",
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
            raise ValueError("Text sources must use UTF-8 encoding") from error
        return [ExtractedPage(text=text, page_number=None)]

    try:
        document = fitz.open(path)
    except fitz.FileDataError as error:
        raise ValueError("The PDF could not be opened") from error

    try:
        pages = [
            ExtractedPage(
                text=document.load_page(index).get_text("text"), page_number=index + 1
            )
            for index in range(document.page_count)
        ]
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

    try:
        pages = extract_pages(get_upload_path(source), source.media_type)
        chunks = [chunk for page in pages for chunk in split_page(page)]
        if not chunks:
            raise ValueError("The source did not contain extractable text")
        embedding_provider = get_embedding_provider()
        embeddings = [
            embedding
            for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE)
            for embedding in embedding_provider.embed(
                [chunk.content for chunk in chunks[start : start + EMBEDDING_BATCH_SIZE]]
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
    except (EmbeddingError, OSError, ValueError, fitz.FileDataError) as error:
        source.status = "failed"
        source.error_message = str(error)[:1000]
        source.processed_at = get_datetime_utc()
    session.add(source)
    session.commit()
    session.refresh(source)


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
        process_source(session=session, source=source)
    except HTTPException:
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


def delete_source_file(source: Source) -> None:
    source_path = get_upload_path(source)
    source_path.unlink(missing_ok=True)
    parent = source_path.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def delete_source(*, session: Session, source: Source) -> None:
    delete_source_file(source)
    session.delete(source)
    session.commit()
