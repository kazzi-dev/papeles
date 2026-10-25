"""Load the sources listed in data/sources.yaml, chunk and embed them, and store them.

Each source either has a `file` (a checked text file under data/, used for agencies whose sites
block automated downloads) or is downloaded from its `url` (HTML or PDF).

Run with: python -m app.ingest
"""

import logging
from io import BytesIO
from pathlib import Path

import httpx
import yaml
from bs4 import BeautifulSoup
from sqlalchemy import delete, select

from app.chunking import chunk_text
from app.db import get_sessionmaker, init_db
from app.embeddings import get_embedder
from app.models import Chunk, Source

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SOURCES_FILE = DATA_DIR / "sources.yaml"


def page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    # Site menus that aren't in <nav> (common on WordPress sites like sss.gov.ph).
    for tag in soup.select('[role="navigation"], ul[class*="menu"], div[class*="menu"]'):
        tag.decompose()
    main = soup.find("main") or soup.body or soup
    return main.get_text(" ", strip=True)


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    # Government PDFs are often slightly malformed; pypdf copes but logs a line per object.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)


def load_text(entry: dict, http: httpx.Client, data_dir: Path = DATA_DIR) -> str:
    if "file" in entry:
        return (data_dir / entry["file"]).read_text(encoding="utf-8")

    resp = http.get(entry["url"], headers={"User-Agent": "PapelesBot/0.1"})
    resp.raise_for_status()
    if "application/pdf" in resp.headers.get("content-type", ""):
        return pdf_text(resp.content)
    return page_text(resp.text)


def main() -> None:
    init_db()
    entries = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    embedder = get_embedder()

    with httpx.Client(timeout=60, follow_redirects=True) as http, get_sessionmaker()() as session:
        # Drop sources that were removed from sources.yaml.
        session.execute(delete(Source).where(Source.slug.not_in([e["slug"] for e in entries])))
        session.commit()

        for entry in entries:
            try:
                text = load_text(entry, http)
            except (httpx.HTTPError, OSError) as exc:
                print(f"skip {entry['slug']}: {exc}")
                continue

            pieces = chunk_text(text)
            if not pieces:
                print(f"skip {entry['slug']}: no text (page may need JavaScript; add a file)")
                continue
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
