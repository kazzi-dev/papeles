import pytest

from app.rag import MAX_CHUNKS_PER_PAGE, RetrievedChunk, detect_agencies, diversify


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Nakalimutan ko ang Pag-IBIG MID number ko", {"Pag-IBIG Fund"}),
        ("Paano kumuha ng SSS number?", {"SSS"}),
        ("Unsaon pagkuha og driver's license?", {"LTO"}),
        ("How much is a student permit?", {"LTO"}),
        ("How do I order a birth certificate online?", {"PSA"}),
        ("How do I register for PhilSys national ID?", {"PSA"}),
        ("Paano mag-renew ng passport?", {"DFA"}),
        ("Ano ang requirements para sa NBI clearance?", {"NBI"}),
        ("Do I need my SSS and PhilHealth numbers for work?", {"SSS", "PhilHealth"}),
        ("What do I need to start working?", set()),
    ],
)
def test_detect_agencies(question, expected):
    assert detect_agencies(question) == expected


def test_detect_agencies_avoids_short_word_false_matches():
    # "mid" alone, or "sss" inside another word, must not trigger.
    assert detect_agencies("What happens mid-year to classes?") == set()


def chunk(url: str, i: int) -> RetrievedChunk:
    return RetrievedChunk(f"text {i}", "t", url, "A")


def test_diversify_caps_chunks_per_page():
    ranked = [chunk("big", i) for i in range(10)] + [chunk("small", 0), chunk("other", 0)]
    picked = diversify(ranked, top_k=5)

    assert [c.url for c in picked].count("big") == MAX_CHUNKS_PER_PAGE
    assert {c.url for c in picked} == {"big", "small", "other"}


def test_diversify_keeps_rank_order():
    ranked = [chunk("a", 0), chunk("b", 0), chunk("a", 1)]
    assert diversify(ranked, top_k=5) == ranked
