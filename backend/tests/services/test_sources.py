import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest import MonkeyPatch

from app.core.config import settings
from app.models import Source
from app.services.sources import (
    CHUNK_SIZE,
    ExtractedPage,
    process_source,
    split_page,
)


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
