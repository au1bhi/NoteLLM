from collections.abc import Sequence
from typing import Protocol

import httpx

from app.core.config import settings
from app.services.provider_settings import ProviderConfig, resolve_api_base


class EmbeddingError(Exception):
    """Raised when a source cannot be embedded by the configured provider."""


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.config.base_url or not self.config.api_key or not self.config.model:
            raise EmbeddingError(
                "Embedding is not configured. Add your API key in Settings, or "
                "set EMBEDDING_BASE_URL, EMBEDDING_API_KEY, and EMBEDDING_MODEL "
                "on the server."
            )

        endpoint = (
            f"{resolve_api_base(self.config.base_url, self.config.api_format)}"
            "/embeddings"
        )
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json={
                    "model": self.config.model,
                    "input": list(texts),
                    "dimensions": settings.EMBEDDING_DIMENSIONS,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()["data"]
            vectors = [
                item["embedding"]
                for item in sorted(data, key=lambda item: item["index"])
            ]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingError("嵌入模型未返回有效向量") from error

        if len(vectors) != len(texts) or any(
            len(vector) != settings.EMBEDDING_DIMENSIONS for vector in vectors
        ):
            raise EmbeddingError(
                f"嵌入模型必须返回 {settings.EMBEDDING_DIMENSIONS} 维向量"
            )
        return [[float(value) for value in vector] for vector in vectors]


def get_embedding_provider(
    config: ProviderConfig | None = None,
) -> EmbeddingProvider:
    if config is None:
        config = ProviderConfig(
            base_url=str(settings.EMBEDDING_BASE_URL)
            if settings.EMBEDDING_BASE_URL
            else "",
            api_key=settings.EMBEDDING_API_KEY or "",
            model=settings.EMBEDDING_MODEL or "",
        )
    return OpenAICompatibleEmbeddingProvider(config)
