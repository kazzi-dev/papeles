from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """Runs a small ONNX model locally, so embeddings cost nothing and need no API key."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]


@lru_cache
def get_embedder() -> Embedder:
    return FastEmbedder(get_settings().embedding_model)
