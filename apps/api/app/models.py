from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db import Base


class Source(Base):
    """One official page we answer from, e.g. the DFA passport requirements page."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    agency: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    # Plain JSON on SQLite, for running locally without Postgres (see rag._rank_in_python).
    embedding: Mapped[list[float]] = mapped_column(
        Vector(get_settings().embedding_dim).with_variant(JSON(), "sqlite")
    )

    source: Mapped[Source] = relationship(back_populates="chunks")
