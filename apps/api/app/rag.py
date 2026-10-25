import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PROVIDER_DEFAULTS, get_settings
from app.embeddings import Embedder
from app.models import Chunk, Source

Lang = Literal["en", "tl", "ceb"]

LANG_NAMES: dict[Lang, str] = {"en": "English", "tl": "Tagalog", "ceb": "Bisaya (Cebuano)"}

SYSTEM_PROMPT = """You are Papeles, a helper for Filipinos dealing with government paperwork \
(passport, NBI clearance, PhilSys ID, SSS, PhilHealth, Pag-IBIG, LTO, PSA documents).

Use only the numbered sources in the user's message. People will act on your answer, so a \
requirement that isn't really required costs them a wasted trip:
- Every requirement, step, fee and deadline you list must be stated in the sources. Do not add \
items from general knowledge, even ones that are commonly required elsewhere.
- End each item with its citation in square brackets, like [1] or [2].
- If the sources cover only part of the question, answer that part and say plainly what they \
don't cover. If they cover none of it, say so and point to the agency's official site.

Format in Markdown: a bulleted checklist for requirements, numbered steps for a process, short \
paragraphs otherwise. No headings larger than bold text. Requirements and fees change, so remind \
the user to confirm with the agency when you mention a fee or a deadline."""

# Some models (e.g. gpt-oss) cite as 【1†L1-L4】 or 【1】 instead of [1].
_FANCY_CITATION = re.compile(r"【\s*(\d+)[^】]*】")


def clean_citations(text: str) -> str:
    return _FANCY_CITATION.sub(r"[\1]", text)


@dataclass(frozen=True)
class RetrievedChunk:
    content: str
    title: str
    url: str
    agency: str


class Retriever(Protocol):
    def __call__(self, question: str) -> list[RetrievedChunk]: ...


class Answerer(Protocol):
    def answer(self, question: str, chunks: list[RetrievedChunk], lang: Lang) -> str: ...


def make_retriever(session: Session, embedder: Embedder, top_k: int) -> Retriever:
    columns = select(Chunk.content, Source.title, Source.url, Source.agency).join(Source)

    def retrieve(question: str) -> list[RetrievedChunk]:
        [query_vec] = embedder.embed([question])
        if session.get_bind().dialect.name == "sqlite":
            return _rank_in_python(session, query_vec, top_k)
        rows = session.execute(
            columns.order_by(Chunk.embedding.cosine_distance(query_vec)).limit(top_k)
        ).all()
        return [RetrievedChunk(*row) for row in rows]

    return retrieve


def _rank_in_python(session: Session, query_vec: list[float], top_k: int) -> list[RetrievedChunk]:
    """SQLite fallback for running without Postgres: score every chunk with numpy."""
    import numpy as np

    rows = session.execute(
        select(Chunk.embedding, Chunk.content, Source.title, Source.url, Source.agency).join(Source)
    ).all()
    if not rows:
        return []
    matrix = np.array([r[0] for r in rows], dtype=np.float32)
    query = np.array(query_vec, dtype=np.float32)
    scores = matrix @ query / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(query) + 1e-9)
    best = np.argsort(-scores)[:top_k]
    return [RetrievedChunk(*rows[i][1:]) for i in best]


def group_by_page(chunks: list[RetrievedChunk]) -> dict[str, list[RetrievedChunk]]:
    """Group chunks by source URL, in order of first appearance.

    Citation numbers are per page, so [n] matches the n-th entry of the sources list the API
    returns, not the n-th chunk.
    """
    pages: dict[str, list[RetrievedChunk]] = {}
    for c in chunks:
        pages.setdefault(c.url, []).append(c)
    return pages


def build_user_message(question: str, chunks: list[RetrievedChunk], lang: Lang) -> str:
    sources = "\n\n".join(
        f"[{i}] {group[0].agency} - {group[0].title} ({url})\n"
        + "\n...\n".join(c.content for c in group)
        for i, (url, group) in enumerate(group_by_page(chunks).items(), 1)
    )
    return (
        f"<sources>\n{sources or '(no matching sources)'}\n</sources>\n\n"
        f"Question: {question}\n\nAnswer in {LANG_NAMES[lang]}."
    )


class ClaudeAnswerer:
    def __init__(self, client: anthropic.Anthropic, model: str, effort: str) -> None:
        self._client = client
        self._model = model
        self._effort = effort

    def answer(self, question: str, chunks: list[RetrievedChunk], lang: Lang) -> str:
        response = self._client.beta.messages.create(
            model=self._model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": self._effort},
            messages=[{"role": "user", "content": build_user_message(question, chunks, lang)}],
            # If a safety classifier declines, retry server-side on Anthropic's recommended model.
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        if response.stop_reason == "refusal":
            return "Sorry, I can't help with that question."
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAICompatibleAnswerer:
    """Any provider that speaks the OpenAI chat completions format: Groq, Gemini, OpenRouter."""

    def __init__(self, base_url: str, api_key: str, model: str, http: httpx.Client | None = None):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._http = http or httpx.Client(timeout=60)

    def answer(self, question: str, chunks: list[RetrievedChunk], lang: Lang) -> str:
        resp = self._http.post(
            self._url,
            headers=self._headers,
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_message(question, chunks, lang)},
                ],
            },
        )
        if resp.status_code == 429:
            # Free tiers have tight per-minute and per-day limits.
            return "The free AI quota is used up for now. Please try again in a minute."
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""


class SourcesOnlyAnswerer:
    """Used when no AI key is configured, so the app is still usable for finding pages."""

    def answer(self, question: str, chunks: list[RetrievedChunk], lang: Lang) -> str:
        if not chunks:
            return "AI answers are off (no LLM_API_KEY set) and no matching pages were found."
        return (
            "AI answers are off because LLM_API_KEY isn't set. "
            "These official pages best match your question:"
        )


@lru_cache
def get_answerer() -> Answerer:
    settings = get_settings()
    if settings.llm_provider == "claude":
        key = settings.llm_api_key or settings.anthropic_api_key
        if not key:
            return SourcesOnlyAnswerer()
        return ClaudeAnswerer(
            anthropic.Anthropic(api_key=key),
            settings.llm_model or settings.anthropic_model,
            settings.anthropic_effort,
        )

    if not settings.llm_api_key:
        return SourcesOnlyAnswerer()
    base_url, model = PROVIDER_DEFAULTS[settings.llm_provider]
    return OpenAICompatibleAnswerer(
        settings.llm_base_url or base_url,
        settings.llm_api_key,
        settings.llm_model or model,
    )
