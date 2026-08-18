import uuid
from pathlib import Path
from unittest.mock import MagicMock

import fitz  # type: ignore[import-untyped]
import pytest
from pytest import MonkeyPatch
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Chunk, Notebook, Source
from app.services.sources import (
    CHUNK_SIZE,
    ExtractedPage,
    extract_pages,
    process_source,
    split_page,
)
from tests.utils.user import create_random_user


def _long_page_text(length: int = 2500) -> str:
    unit = "alpha beta gamma\n"
    return (unit * ((length // len(unit)) + 1))[:length]


def test_split_page_default_chunk_size_produces_multiple_chunks() -> None:
    page = ExtractedPage(text=_long_page_text(), page_number=1)
    chunks = list(split_page(page))
    assert len(chunks) > 1
    assert all(chunk.content for chunk in chunks)
    assert max(len(chunk.content) for chunk in chunks) <= CHUNK_SIZE


def test_split_page_custom_size_yields_more_shorter_chunks() -> None:
    page = ExtractedPage(text=_long_page_text(), page_number=1)
    default_chunks = list(split_page(page))
    custom_chunks = list(split_page(page, chunk_size=500, chunk_overlap=50))
    assert len(custom_chunks) > len(default_chunks)
    assert all(len(chunk.content) <= 500 for chunk in custom_chunks)
    assert max(len(chunk.content) for chunk in custom_chunks) < max(
        len(chunk.content) for chunk in default_chunks
    )


def test_split_page_empty_or_whitespace_yields_no_chunks() -> None:
    assert list(split_page(ExtractedPage(text="", page_number=None))) == []
    assert list(split_page(ExtractedPage(text="  \n\t  ", page_number=None))) == []


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [
        (0, 0),
        (-1, 0),
        (100, -1),
        (100, 100),
        (100, 150),
    ],
)
def test_split_page_rejects_invalid_chunk_params(
    chunk_size: int, chunk_overlap: int
) -> None:
    page = ExtractedPage(text="some text", page_number=None)
    with pytest.raises(ValueError):
        split_page(page, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def test_process_source_rejects_invalid_chunk_params() -> None:
    source = Source(
        notebook_id=uuid.uuid4(),
        display_name="notes.txt",
        media_type="text/plain",
        file_size_bytes=1,
        storage_path="notes.txt",
    )
    session = MagicMock()
    with pytest.raises(ValueError, match="chunk_size"):
        process_source(session=session, source=source, chunk_size=0, chunk_overlap=0)
    session.commit.assert_not_called()
    assert source.status == "pending"


def test_process_source_marks_empty_text_failed(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    source = Source(
        notebook_id=uuid.uuid4(),
        display_name="empty.txt",
        media_type="text/plain",
        file_size_bytes=1,
        storage_path="empty.txt",
        status="pending",
    )
    upload_dir = tmp_path / str(source.notebook_id)
    upload_dir.mkdir(parents=True)
    (upload_dir / source.storage_path).write_text("  \n\n  ", encoding="utf-8")

    session = MagicMock()
    process_source(session=session, source=source)

    assert source.status == "failed"
    assert source.error_message is not None
    assert "没有可提取的文本" in source.error_message
    session.commit.assert_called()


def test_process_source_stops_before_provider_when_notebook_is_missing(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    provider_factory = MagicMock()
    monkeypatch.setattr("app.services.sources.get_embedding_provider", provider_factory)
    source = Source(
        notebook_id=uuid.uuid4(),
        display_name="orphan.txt",
        media_type="text/plain",
        file_size_bytes=12,
        storage_path="orphan.txt",
    )
    upload_dir = tmp_path / str(source.notebook_id)
    upload_dir.mkdir(parents=True)
    (upload_dir / source.storage_path).write_text(
        "orphan source text", encoding="utf-8"
    )
    session = MagicMock()
    session.get.return_value = None

    process_source(session=session, source=source)

    assert source.status == "failed"
    assert source.error_message == "资料所属笔记本不存在"
    provider_factory.assert_not_called()


def test_extract_pages_from_real_pdf_preserves_page_numbers(tmp_path: Path) -> None:
    path = tmp_path / "two-pages.pdf"
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "First page evidence")
    second = document.new_page()
    second.insert_text((72, 72), "Second page citation")
    document.save(path)
    document.close()

    pages = extract_pages(path, "application/pdf")

    assert [page.page_number for page in pages] == [1, 2]
    assert "First page evidence" in pages[0].text
    assert "Second page citation" in pages[1].text


def test_corrupt_pdf_marks_source_failed_and_removes_existing_chunks(
    db: Session, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path)
    provider = MagicMock()
    monkeypatch.setattr("app.services.sources.get_embedding_provider", provider)
    user = create_random_user(db)
    notebook = Notebook(owner_id=user.id, title="PDF failure test")
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    source = Source(
        notebook_id=notebook.id,
        display_name="broken.pdf",
        media_type="application/pdf",
        file_size_bytes=17,
        storage_path="broken.pdf",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    db.add(
        Chunk(
            source_id=source.id,
            ordinal=0,
            content="stale chunk",
            page_number=1,
            char_start=0,
            char_end=11,
        )
    )
    db.commit()
    upload_dir = tmp_path / str(notebook.id)
    upload_dir.mkdir(parents=True)
    (upload_dir / source.storage_path).write_bytes(b"not a valid PDF")

    process_source(session=db, source=source)

    db.refresh(source)
    assert source.status == "failed"
    assert source.error_message == "无法打开该 PDF"
    assert db.exec(select(Chunk).where(Chunk.source_id == source.id)).all() == []
    provider.assert_not_called()
