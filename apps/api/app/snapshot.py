"""Save the search index to files in the repo, and load it back.

Embedding every source takes ~1,700 calls' worth of the free Gemini quota, so it's done once on a
developer machine (`python -m app.ingest`, then `python -m app.snapshot export`) and committed.
Deploys then load the files (`python -m app.snapshot import`) with no network calls.

Files in data/index/:
  meta.json        provider, model and dimensions the embeddings were made with
  sources.json     the sources
  chunks.json      each chunk's text and the slug of its source
  embeddings.npy   one float16 row per chunk, in the same order as chunks.json
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_sessionmaker, init_db
from app.models import Chunk, Source

INDEX_DIR = Path(__file__).resolve().parent.parent / "data" / "index"


def current_meta() -> dict:
    s = get_settings()
    model = s.gemini_embedding_model if s.embedding_provider == "gemini" else s.embedding_model
    return {"provider": s.embedding_provider, "model": model, "dimensions": s.embedding_dim}


def export_index(session: Session, out: Path = INDEX_DIR) -> int:
    out.mkdir(parents=True, exist_ok=True)
    sources = session.scalars(select(Source).order_by(Source.id)).all()
    rows = session.execute(
        select(Source.slug, Chunk.content, Chunk.embedding).join(Source).order_by(Chunk.id)
    ).all()

    meta = {**current_meta(), "chunks": len(rows), "exported_at": datetime.now(UTC).isoformat()}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (out / "sources.json").write_text(
        json.dumps(
            [{"slug": s.slug, "agency": s.agency, "title": s.title, "url": s.url} for s in sources],
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    (out / "chunks.json").write_text(
        json.dumps(
            [{"source": slug, "content": text} for slug, text, _ in rows], ensure_ascii=False
        ),
        encoding="utf-8",
    )
    # float16 halves the file size; the precision loss doesn't change search rankings noticeably.
    np.save(out / "embeddings.npy", np.array([e for _, _, e in rows], dtype=np.float16))
    return len(rows)


def import_index(session: Session, src: Path = INDEX_DIR) -> int:
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    expected = current_meta()
    mismatched = {k: (meta.get(k), v) for k, v in expected.items() if meta.get(k) != v}
    if mismatched:
        raise SystemExit(
            f"The saved index was built with different embedding settings: {mismatched} "
            "(saved, configured). Re-run the ingest and export with the current settings."
        )

    sources = json.loads((src / "sources.json").read_text(encoding="utf-8"))
    chunks = json.loads((src / "chunks.json").read_text(encoding="utf-8"))
    vectors = np.load(src / "embeddings.npy").astype(np.float32)
    if len(chunks) != len(vectors):
        raise SystemExit(
            f"chunks.json has {len(chunks)} rows but embeddings.npy has {len(vectors)}"
        )

    session.execute(delete(Chunk))
    session.execute(delete(Source))
    by_slug = {s["slug"]: Source(**s) for s in sources}
    session.add_all(by_slug.values())
    session.flush()
    session.add_all(
        Chunk(source_id=by_slug[c["source"]].id, content=c["content"], embedding=v.tolist())
        for c, v in zip(chunks, vectors, strict=True)
    )
    session.commit()
    return len(chunks)


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in {"export", "import"}:
        raise SystemExit("usage: python -m app.snapshot export|import")
    init_db()
    with get_sessionmaker()() as session:
        if command == "export":
            print(f"exported {export_index(session)} chunks to {INDEX_DIR}")
        else:
            print(f"imported {import_index(session)} chunks from {INDEX_DIR}")


if __name__ == "__main__":
    main()
