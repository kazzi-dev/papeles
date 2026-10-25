"""Fetch the official pages listed in data/sources.yaml, chunk and embed them, and store them.

Run with: python -m app.ingest
"""

from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.chunking import chunk_text
from app.db import get_sessionmaker, init_db
from app.embeddings import get_embedder
from app.models import Chunk, Source

SOURCES_FILE = Path(__file__).resolve().parent.parent / "data" / "sources.yaml"


def page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.body or soup
    return main.get_text(" ", strip=True)


def main() -> None:
    init_db()
    entries = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    embedder = get_embedder()

    with httpx.Client(timeout=30, follow_redirects=True) as http, get_sessionmaker()() as session:
        for entry in entries:
            try:
                resp = http.get(entry["url"], headers={"User-Agent": "PapelesBot/0.1"})
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"skip {entry['slug']}: {exc}")
                continue

            pieces = chunk_text(page_text(resp.text))
            vectors = embedder.embed(pieces)

            source = session.scalar(select(Source).where(Source.slug == entry["slug"]))
            if source is None:
                source = Source(slug=entry["slug"])
                session.add(source)
            source.agency = entry["agency"]
            source.title = entry["title"]
            source.url = entry["url"]
            source.chunks = [
                Chunk(content=p, embedding=v) for p, v in zip(pieces, vectors, strict=True)
            ]
            session.commit()
            print(f"ok   {entry['slug']}: {len(pieces)} chunks")


if __name__ == "__main__":
    main()
