import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
log = logging.getLogger("papeles")


# Registered before CORS so CORS wraps it: an unexpected error then still gets CORS headers, and
# the website can show this message instead of the browser's opaque "Failed to fetch".
@app.middleware("http")
async def readable_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our side. Please try again in a moment."},
        )


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
    # Opening the API's URL in a browser should say what this is.
    return {"name": "Papeles API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
