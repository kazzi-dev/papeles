from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.embeddings import get_embedder
from app.routers import ask


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Load the embedding model now, so the first visitor doesn't wait for it.
    get_embedder()
    yield


app = FastAPI(title="Papeles API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(ask.router)


@app.get("/")
def root() -> dict[str, str]:
    # Hosts like Hugging Face Spaces show the root URL, so say what this is.
    return {"name": "Papeles API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
