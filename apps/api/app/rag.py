import re
import time
from collections.abc import Callable
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

# Heading for the part of an answer that comes from the model's general knowledge. Fixed per
# language so the web app can recognise and style it.
GENERAL_HEADING: dict[Lang, str] = {
    "en": "General guidance (not from an official source, please verify)",
    "tl": "Pangkalahatang gabay (hindi mula sa opisyal na source, paki-verify)",
    "ceb": "Kinatibuk-ang giya (dili gikan sa opisyal nga source, palihug i-verify)",
}

SYSTEM_PROMPT = """You are Papeles, a helper for Filipinos dealing with government paperwork \
(passport, NBI clearance, PhilSys ID, SSS, PhilHealth, Pag-IBIG, LTO, PSA documents).

Your job is to actually answer: someone asking "what do I need for X" should finish reading \
with a usable checklist and next steps, not a link to go and find out themselves.

Write the answer in up to two parts:

1. What the numbered sources say. Every item here must be stated in the sources and end with \
its citation in square brackets, like [1] or [2]. Leave this part out if the sources don't \
help with the question.

2. If the sources leave gaps for what the person needs (for example which valid IDs are \
accepted, the documents to bring, the usual steps), fill them from your general knowledge of \
Philippine government processes, under the exact bold heading given in the user's message. \
Items in this part have no citations. In this part:
- Do not state phone numbers, email addresses, URLs, exact fee amounts, processing times, or \
form numbers and codes (like "Form 5"); say where to check them instead.
- Include only what is widely known and has been stable for years. Leave out anything you are \
unsure of; a shorter list is better than a wrong item.
- Keep it to the essentials: at most about 6 checklist items and 6 steps.
- Many agencies have moved registration online; don't send people to a branch for something \
that is usually done online.

Never move general-knowledge items into part 1, and never cite them.

Format in Markdown: a bulleted checklist for requirements, numbered steps for a process, short \
paragraphs otherwise. No headings larger than bold text. Keep it concise. End with one short \
line reminding the user that requirements and fees change, so confirm with the agency."""

# Some models (e.g. gpt-oss) cite as 【1†L1-L4】 or 【1】 instead of [1].
_FANCY_CITATION = re.compile(r"【\s*(\d+)[^】]*】")


def clean_citations(text: str) -> str:
    return _FANCY_CITATION.sub(r"[\1]", text)


def cited_numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\[(\d+)\]", text)}


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


# Words that name an agency or a document only it issues, in English, Tagalog and Bisaya. When a
# question mentions one, we search only that agency's sources. This matters because one large
# source (the 1,500-chunk SSS Citizen's Charter) otherwise crowds out small ones in vector search.
AGENCY_KEYWORDS: dict[str, list[str]] = {
    "SSS": [r"\bsss\b", "social security", r"\bss (number|no)", "my.sss", r"\bumid\b"],
    "PhilHealth": ["philhealth", r"\bpmrf\b"],
    "Pag-IBIG Fund": [
        "pag-ibig",
        "pagibig",
        "pag ibig",
        r"\bhdmf\b",
        r"\bmid (number|no)",
        r"\bmp2\b",
    ],
    "PSA": [
        r"\bpsa\b",
        "birth certificate",
        "marriage certificate",
        "death certificate",
        "cenomar",
        "cenodeath",
        "serbilis",
        "philsys",
        "national id",
        "philid",
        "birth cert",
    ],
    "NBI": [r"\bnbi\b"],
    "LTO": [
        r"\blto\b",
        "driver",
        "license",
        "licence",
        "lisensya",
        "lisensiya",
        "student permit",
        r"\bmagmaneho\b",
        r"\bpagmaneho\b",
    ],
    "DFA": [r"\bdfa\b", "passport", "pasaporte"],
}

# A page may contribute at most this many chunks, so several pages get a say.
MAX_CHUNKS_PER_PAGE = 3


def detect_agencies(question: str) -> set[str]:
    q = question.lower()
    return {
        agency
        for agency, patterns in AGENCY_KEYWORDS.items()
        if any(re.search(p, q) for p in patterns)
    }


def diversify(ranked: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    """Keep the best-ranked chunks, but no more than MAX_CHUNKS_PER_PAGE from one page."""
    picked: list[RetrievedChunk] = []
    per_page: dict[str, int] = {}
    for c in ranked:
        if per_page.get(c.url, 0) < MAX_CHUNKS_PER_PAGE:
            picked.append(c)
            per_page[c.url] = per_page.get(c.url, 0) + 1
            if len(picked) == top_k:
                break
    return picked


def make_retriever(session: Session, embedder: Embedder, top_k: int) -> Retriever:
    def retrieve(question: str) -> list[RetrievedChunk]:
        [query_vec] = embedder.embed([question], kind="query")
        agencies = detect_agencies(question)
        candidates = top_k * 4
        if session.get_bind().dialect.name == "sqlite":
            ranked = _rank_in_python(session, query_vec, candidates, agencies)
        else:
            query = select(Chunk.content, Source.title, Source.url, Source.agency).join(Source)
            if agencies:
                query = query.where(Source.agency.in_(agencies))
            rows = session.execute(
                query.order_by(Chunk.embedding.cosine_distance(query_vec)).limit(candidates)
            ).all()
            ranked = [RetrievedChunk(*row) for row in rows]
        return diversify(ranked, top_k)

    return retrieve


def _rank_in_python(
    session: Session, query_vec: list[float], limit: int, agencies: set[str]
) -> list[RetrievedChunk]:
    """SQLite fallback for running without Postgres: score every chunk with numpy."""
    import numpy as np

    query = select(Chunk.embedding, Chunk.content, Source.title, Source.url, Source.agency).join(
        Source
    )
    if agencies:
        query = query.where(Source.agency.in_(agencies))
    # Skip chunks embedded with a different model (e.g. while the index is being rebuilt after
    # switching embedding providers) instead of failing the whole search.
    rows = [r for r in session.execute(query).all() if len(r[0]) == len(query_vec)]
    if not rows:
        return []
    matrix = np.array([r[0] for r in rows], dtype=np.float32)
    q = np.array(query_vec, dtype=np.float32)
    scores = matrix @ q / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q) + 1e-9)
    best = np.argsort(-scores)[:limit]
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
        f"Question: {question}\n\n"
        f"Heading for general guidance, if needed: **{GENERAL_HEADING[lang]}**\n\n"
        f"Answer in {LANG_NAMES[lang]}."
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

    # Free tiers have tight per-minute limits; wait out short ones rather than failing.
    MAX_RETRIES = 2
    MAX_WAIT_SECONDS = 20.0

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._http = http or httpx.Client(timeout=60)
        self._sleep = sleep

    def answer(self, question: str, chunks: list[RetrievedChunk], lang: Lang) -> str:
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(question, chunks, lang)},
            ],
        }
        for attempt in range(self.MAX_RETRIES + 1):
            resp = self._http.post(self._url, headers=self._headers, json=body)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"] or ""
            wait = _retry_after_seconds(resp)
            if attempt == self.MAX_RETRIES or wait > self.MAX_WAIT_SECONDS:
                break
            self._sleep(wait)
        return "The free AI quota is used up for now. Please try again in a minute."


def _retry_after_seconds(resp: httpx.Response) -> float:
    try:
        return float(resp.headers.get("retry-after", "5"))
    except ValueError:
        return 5.0


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
