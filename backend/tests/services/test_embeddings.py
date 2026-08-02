from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services.embeddings import EmbeddingError, get_embedding_provider


def test_embedding_provider_requires_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", None)
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", None)
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", None)

    with pytest.raises(EmbeddingError, match="not configured"):
        get_embedding_provider().embed(["question"])


def test_embedding_provider_orders_vectors_and_validates_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMBEDDING_BASE_URL", "https://models.example/v1")
    monkeypatch.setattr(settings, "EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSIONS", 2)

    captured: dict[str, Any] = {}

    def fake_pinned_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        assert method == "POST"
        captured["url"] = url
        captured["headers"] = kwargs.get("headers", {})
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [2, 2]},
                    {"index": 0, "embedding": [1, 1]},
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("app.services.embeddings.pinned_request", fake_pinned_request)
    assert get_embedding_provider().embed(["first", "second"]) == [
        [1.0, 1.0],
        [2.0, 2.0],
    ]
    assert captured["url"] == "https://models.example/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"] == {
        "model": "test-embedding",
        "input": ["first", "second"],
        "dimensions": 2,
    }
