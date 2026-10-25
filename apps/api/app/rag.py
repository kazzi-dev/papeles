from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import Embedder
from app.models import Chunk, Source

Lang = Literal["en", "tl", "ceb"]

LANG_NAMES: dict[Lang, str] = {"en": "English", "tl": "Tagalog", "ceb": "Bisaya (Cebuano)"}

SYSTEM_PROMPT = """You are Papeles, a helper for Filipinos dealing with government paperwork \
(passport, NBI clearance, PhilSys ID, SSS, PhilHealth, Pag-IBIG, LTO, PSA documents).

Answer only from the numbered sources in the user's message. Cite them inline like [1] or [2]. \
If the sources don't cover the question, say so plainly and point to the agency's official site \
instead of guessing. Requirements and fees change, so remind the user to confirm with the agency \
when you mention a fee or a deadline. Keep answers short and practical: a checklist when listing \
requirements, numbered steps when describing a process."""


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
    def retrieve(question: str) -> list[RetrievedChunk]:
        [query_vec] = embedder.embed([question])
        rows = session.execute(
            select(Chunk.content, Source.title, Source.url, Source.agency)
            .join(Source)
            .order_by(Chunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        ).all()
        return [RetrievedChunk(*row) for row in rows]

    return retrieve


def build_user_message(question: str, chunks: list[RetrievedChunk], lang: Lang) -> str:
    sources = "\n\n".join(
        f"[{i}] {c.agency} - {c.title} ({c.url})\n{c.content}" for i, c in enumerate(chunks, 1)
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


@lru_cache
def get_answerer() -> Answerer:
    settings = get_settings()
    return ClaudeAnswerer(
        anthropic.Anthropic(), settings.anthropic_model, settings.anthropic_effort
    )
