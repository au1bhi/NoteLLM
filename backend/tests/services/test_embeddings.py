from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services.embeddings import EmbeddingError, OpenAICompatibleEmbeddingProvider


def test_embedding_provider_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_BASE_URL", None)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", None)

    with pytest.raises(EmbeddingError, match="not configured"):
        OpenAICompatibleEmbeddingProvider().embed(["question"])


def test_embedding_provider_orders_vectors_and_validates_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://models.example/v1")
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "EMBEDDING_MODEL", "test-embedding")
    monkeypatch.setattr(settings, "EMBEDDING_DIMENSIONS", 2)

    def post(url: str, **kwargs: Any) -> httpx.Response:
        assert url == "https://models.example/v1/embeddings"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["json"] == {"model": "test-embedding", "input": ["first", "second"]}
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [2, 2]}, {"index": 0, "embedding": [1, 1]}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    assert OpenAICompatibleEmbeddingProvider().embed(["first", "second"]) == [
        [1.0, 1.0],
        [2.0, 2.0],
    ]
