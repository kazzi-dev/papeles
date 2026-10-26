import hashlib
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from typing import Literal, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    # Free-tier limits (AI Studio → Rate limit): 100 requests/min, where every text in a batch
    # counts as one request; 30,000 input tokens/min; 1,000 requests/day. Stay under the
    # per-minute ones ourselves: rejected requests still count against the daily quota.
    BATCH_SIZE = 40
    TEXTS_PER_MINUTE = 90
    TOKENS_PER_MINUTE = 25_000
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
        self._sent: deque[tuple[float, int, int]] = deque()  # (time, texts, tokens) per call

    @staticmethod
    def estimate_tokens(text: str) -> int:
        # ~4 characters per token for English; 3 leaves headroom for Tagalog and numbers.
        return len(text) // 3 + 1

    def _wait_for_budget(self, n: int, tokens: int) -> None:
        while True:
            now = self._clock()
            while self._sent and self._sent[0][0] <= now - 60:
                self._sent.popleft()
            used_texts = sum(t for _, t, _ in self._sent)
            used_tokens = sum(k for _, _, k in self._sent)
            if (
                used_texts + n <= self.TEXTS_PER_MINUTE
                and used_tokens + tokens <= self.TOKENS_PER_MINUTE
            ):
                return
            self._sleep(self._sent[0][0] + 60 - now + 0.5)

    def batches(self, texts: list[str]) -> list[list[str]]:
        """Split texts so each batch fits both per-minute budgets on its own."""
        out: list[list[str]] = []
        current: list[str] = []
        tokens = 0
        for text in texts:
            t = self.estimate_tokens(text)
            if current and (
                len(current) >= self.BATCH_SIZE or tokens + t > self.TOKENS_PER_MINUTE // 2
            ):
                out.append(current)
                current, tokens = [], 0
            current.append(text)
            tokens += t
        if current:
            out.append(current)
        return out

    def embed(self, texts: list[str], kind: Kind = "document") -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in self.batches(texts):
            vectors.extend(self._embed_batch(batch, kind))
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
            tokens = sum(self.estimate_tokens(t) for t in texts)
            self._wait_for_budget(len(texts), tokens)
            resp = self._http.post(self._url, headers=self._headers, json=body)
            self._sent.append((self._clock(), len(texts), tokens))
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


class CachedEmbedder:
    """Wraps an embedder with a persistent cache, saving after every batch.

    Used by the ingest: if the free daily quota runs out halfway, the next run reuses everything
    already embedded instead of paying for it again.
    """

    def __init__(self, inner: Embedder, model_id: str, session: Session, batch_size: int = 40):
        self._inner = inner
        self._model_id = model_id
        self._session = session
        self._batch_size = batch_size

    def _key(self, text: str, kind: Kind) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self._model_id}:{kind}:{digest}"

    def embed(self, texts: list[str], kind: Kind = "document") -> list[list[float]]:
        from app.models import EmbeddingCache

        keys = [self._key(t, kind) for t in texts]
        found = {
            row.key: row.embedding
            for row in self._session.scalars(
                select(EmbeddingCache).where(EmbeddingCache.key.in_(set(keys)))
            )
        }
        missing = [i for i, k in enumerate(keys) if k not in found]
        for start in range(0, len(missing), self._batch_size):
            group = missing[start : start + self._batch_size]
            vectors = self._inner.embed([texts[i] for i in group], kind)
            for i, vec in zip(group, vectors, strict=True):
                found[keys[i]] = vec
                self._session.merge(EmbeddingCache(key=keys[i], embedding=vec))
            self._session.commit()
        return [found[k] for k in keys]


def embedding_model_id() -> str:
    s = get_settings()
    if s.embedding_provider == "gemini":
        return f"gemini/{s.gemini_embedding_model}/{s.embedding_dim}"
    return f"local/{s.embedding_model}"


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
