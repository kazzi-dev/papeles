import pytest

from app.chunking import chunk_text


def test_short_text_is_one_chunk():
    assert chunk_text("Bring two valid IDs.") == ["Bring two valid IDs."]


def test_long_text_overlaps_and_covers_everything():
    text = " ".join(f"Requirement number {i} is needed." for i in range(200))
    chunks = chunk_text(text, size=300, overlap=50)

    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    assert chunks[0].startswith("Requirement number 0")
    assert chunks[-1].endswith("Requirement number 199 is needed.")


def test_overlap_must_be_smaller_than_size():
    with pytest.raises(ValueError):
        chunk_text("abc", size=10, overlap=10)
