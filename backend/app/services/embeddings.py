from collections.abc import Sequence
from typing import Protocol

import httpx

from app.core.config import settings


class EmbeddingError(Exception):
    """Raised when a source cannot be embedded by the configured provider."""


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if (
            not settings.EMBEDDING_BASE_URL
            or not settings.EMBEDDING_API_KEY
            or not settings.EMBEDDING_MODEL
        ):
            raise EmbeddingError(
                "Embedding is not configured. Set EMBEDDING_BASE_URL, EMBEDDING_API_KEY, and EMBEDDING_MODEL."
            )

        endpoint = f"{str(settings.EMBEDDING_BASE_URL).rstrip('/')}/embeddings"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
                json={
                    "model": settings.EMBEDDING_MODEL,
                    "input": list(texts),
                    "dimensions": settings.EMBEDDING_DIMENSIONS,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()["data"]
            vectors = [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingError("The embedding provider did not return valid vectors") from error

        if len(vectors) != len(texts) or any(
            len(vector) != settings.EMBEDDING_DIMENSIONS for vector in vectors
        ):
            raise EmbeddingError(
                f"The embedding provider must return {settings.EMBEDDING_DIMENSIONS}-dimension vectors"
            )
        return [[float(value) for value in vector] for vector in vectors]


def get_embedding_provider() -> EmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider()
