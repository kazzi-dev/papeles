from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.embeddings import get_embedder
from app.rag import (
    Answerer,
    Lang,
    Retriever,
    clean_citations,
    get_answerer,
    group_by_page,
    make_retriever,
)

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    lang: Lang = "en"


class SourceOut(BaseModel):
    title: str
    url: str
    agency: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceOut]


def get_retriever(session: Annotated[Session, Depends(get_session)]) -> Retriever:
    return make_retriever(session, get_embedder(), get_settings().top_k)


@router.post("/ask")
def ask(
    body: AskRequest,
    retrieve: Annotated[Retriever, Depends(get_retriever)],
    answerer: Annotated[Answerer, Depends(get_answerer)],
) -> AskResponse:
    chunks = retrieve(body.question)
    answer = clean_citations(answerer.answer(body.question, chunks, body.lang))

    # One entry per page, in the same order the prompt numbered them, so [n] matches.
    sources = [
        SourceOut(title=group[0].title, url=url, agency=group[0].agency)
        for url, group in group_by_page(chunks).items()
    ]
    return AskResponse(answer=answer, sources=sources)
