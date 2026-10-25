from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.embeddings import QuotaExhausted, get_embedder
from app.rag import (
    Answerer,
    Lang,
    Retriever,
    SourcesOnlyAnswerer,
    cited_numbers,
    clean_citations,
    get_answerer,
    group_by_page,
    make_retriever,
)
from app.ratelimit import rate_limit

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    lang: Lang = "en"


class SourceOut(BaseModel):
    n: int  # the number the answer cites it by, e.g. [2]
    title: str
    url: str
    agency: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]


def get_retriever(session: Annotated[Session, Depends(get_session)]) -> Retriever:
    return make_retriever(session, get_embedder(), get_settings().top_k)


# The rate limit runs first, so a blocked request never loads the model or calls the AI.
@router.post("/ask", dependencies=[Depends(rate_limit)])
def ask(
    body: AskRequest,
    retrieve: Annotated[Retriever, Depends(get_retriever)],
    answerer: Annotated[Answerer, Depends(get_answerer)],
) -> AskResponse:
    try:
        chunks = retrieve(body.question)
    except QuotaExhausted as exc:
        raise HTTPException(
            status_code=503,
            detail="Search has reached its free daily limit. Please try again tomorrow.",
            headers={"Retry-After": str(int(exc.retry_after))},
        ) from exc
    answer = clean_citations(answerer.answer(body.question, chunks, body.lang))

    # One entry per page, numbered the same way the prompt numbered them, so [n] matches.
    sources = [
        SourceOut(n=n, title=group[0].title, url=url, agency=group[0].agency)
        for n, (url, group) in enumerate(group_by_page(chunks).items(), 1)
    ]
    # Show only the pages the answer cites. Without an AI key the pages are the whole answer.
    if not isinstance(answerer, SourcesOnlyAnswerer):
        cited = cited_numbers(answer)
        sources = [s for s in sources if s.n in cited]
    return AskResponse(answer=answer, sources=sources)
