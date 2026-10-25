import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Literal, Protocol

import httpx

from app.config import get_settings

# Documents and queries are embedded differently by some models (Gemini), so callers say which.
Kind = Literal["document", "query"]


class QuotaExhausted(Exception):
    """The embedding API's daily quota is used up."""

    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        hours = retry_after / 3600
        super().__init__(f"Embedding quota used up; try again in about {hours:.1f} hours")


class Embedder(Protocol):
    def embed(self, texts: list[str], kind: Kind = "document") -> list[list[float]]: ...


class FastEmbedder:
    """Runs a small ONNX model locally: free and keyless, but needs ~600 MB of memory."""

    def __init__(self, model_name: str, cache_dir: str | None = None) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed(self, texts: list[str], kind: Kind = "document") -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]


class GeminiEmbedder:
    """Google's Gemini embedding API: free tier, multilingual, and nothing to load in memory."""

    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
    # The free tier counts every text in a batch as one request, 100 per minute. Stay a little
    # under that ourselves instead of hammering the API into 429s during ingest.
    BATCH_SIZE = 90
    TEXTS_PER_MINUTE = 90
    MAX_RETRIES = 5
    MAX_WAIT_SECONDS = 120
    TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = self.URL.format(model=model)
        self._model = f"models/{model}"
        self._headers = {"x-goog-api-key": api_key}
        self._dimensions = dimensions
        self._http = http or httpx.Client(timeout=60)
        self._sleep = sleep
        self._clock = clock
        self._sent: deque[tuple[float, int]] = deque()  # (time, number of texts) per call

    def _wait_for_budget(self, n: int) -> None:
        while True:
            now = self._clock()
            while self._sent and self._sent[0][0] <= now - 60:
                self._sent.popleft()
            if sum(count for _, count in self._sent) + n <= self.TEXTS_PER_MINUTE:
                return
            self._sleep(self._sent[0][0] + 60 - now + 0.5)

    def embed(self, texts: list[str], kind: Kind = "document") -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            vectors.extend(self._embed_batch(texts[start : start + self.BATCH_SIZE], kind))
        return vectors

    def _embed_batch(self, texts: list[str], kind: Kind) -> list[list[float]]:
        body = {
            "requests": [
                {
                    "model": self._model,
                    "content": {"parts": [{"text": text}]},
                    "taskType": self.TASK_TYPES[kind],
                    "outputDimensionality": self._dimensions,
                }
                for text in texts
            ]
        }
        for attempt in range(self.MAX_RETRIES + 1):
            self._wait_for_budget(len(texts))
            resp = self._http.post(self._url, headers=self._headers, json=body)
            self._sent.append((self._clock(), len(texts)))
            if resp.status_code == 429:
                wait = _retry_after(resp, default=min(60.0, 5.0 * 2**attempt))
                if wait > self.MAX_WAIT_SECONDS:
                    # The free tier also allows 1,000 embeddings per day; waiting won't help.
                    raise QuotaExhausted(wait)
                if attempt < self.MAX_RETRIES:
                    self._sleep(wait)
                    continue
            resp.raise_for_status()
            return [e["values"] for e in resp.json()["embeddings"]]
        raise RuntimeError("unreachable")


def _retry_after(resp: httpx.Response, default: float) -> float:
    """Gemini puts the wait in the error body ("retryDelay": "24s"); some hosts use the header."""
    try:
        return float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        pass
    try:
        for detail in resp.json()["error"]["details"]:
            if "retryDelay" in detail:
                return float(detail["retryDelay"].rstrip("s")) + 1
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return default


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    if settings.embedding_provider == "gemini":
        if not settings.gemini_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER is gemini but GEMINI_API_KEY is not set")
        return GeminiEmbedder(
            settings.gemini_api_key, settings.gemini_embedding_model, settings.embedding_dim
        )
    return FastEmbedder(settings.embedding_model, settings.embedding_cache_dir or None)
