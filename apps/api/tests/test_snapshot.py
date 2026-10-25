import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Chunk, Source
from app.snapshot import current_meta, export_index, import_index


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def seed(session: Session) -> None:
    dim = current_meta()["dimensions"]
    sss = Source(slug="sss", agency="SSS", title="Get an SS number", url="https://sss.gov.ph/a")
    lto = Source(slug="lto", agency="LTO", title="Student permit", url="https://lto.gov.ph/b")
    sss.chunks = [Chunk(content="Apply online.", embedding=[0.5] * dim)]
    lto.chunks = [
        Chunk(content="PHP 250 total.", embedding=[0.25] * dim),
        Chunk(content="Bawal ang walang lisensya.", embedding=[-1.0] * dim),
    ]
    session.add_all([sss, lto])
    session.commit()


def test_export_then_import_round_trips(session, tmp_path):
    seed(session)
    assert export_index(session, tmp_path) == 3

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as fresh:
        assert import_index(fresh, tmp_path) == 3
        rows = fresh.execute(
            select(Source.slug, Chunk.content, Chunk.embedding).join(Source).order_by(Chunk.id)
        ).all()

    assert [(slug, text) for slug, text, _ in rows] == [
        ("sss", "Apply online."),
        ("lto", "PHP 250 total."),
        ("lto", "Bawal ang walang lisensya."),
    ]
    assert rows[1][2][0] == pytest.approx(0.25)
    assert rows[2][2][0] == pytest.approx(-1.0)


def test_import_replaces_existing_data(session, tmp_path):
    seed(session)
    export_index(session, tmp_path)
    import_index(session, tmp_path)  # importing into the same DB must not duplicate rows
    assert session.scalar(select(func.count()).select_from(Chunk)) == 3
    assert session.scalar(select(func.count()).select_from(Source)) == 2


def test_import_refuses_index_built_with_other_settings(session, tmp_path):
    import json

    seed(session)
    export_index(session, tmp_path)
    meta = json.loads((tmp_path / "meta.json").read_text())
    meta["dimensions"] = 1
    (tmp_path / "meta.json").write_text(json.dumps(meta))

    with pytest.raises(SystemExit, match="different embedding settings"):
        import_index(session, tmp_path)
