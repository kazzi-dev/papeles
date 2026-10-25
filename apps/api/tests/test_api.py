import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import RetrievedChunk, build_user_message, get_answerer
from app.routers.ask import get_retriever

CHUNKS = [
    RetrievedChunk("Bring a PSA birth certificate.", "Passport", "https://a.gov.ph/p", "DFA"),
    RetrievedChunk("Appointments are online.", "Passport", "https://a.gov.ph/p", "DFA"),
]


class FakeAnswerer:
    def __init__(self):
        self.calls = []

    def answer(self, question, chunks, lang):
        self.calls.append((question, chunks, lang))
        return "Bring your PSA birth certificate [1]."


# Not entered as a context manager, so the lifespan (which needs Postgres) never runs.
client = TestClient(app)


@pytest.fixture(autouse=True)
def fake_answerer():
    # FastAPI resolves dependencies even for invalid requests, so every test needs these stubs
    # to keep the real embedding model and Claude client from loading.
    fake = FakeAnswerer()
    app.dependency_overrides[get_retriever] = lambda: lambda q: CHUNKS
    app.dependency_overrides[get_answerer] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_ask_returns_answer_and_deduplicated_sources(fake_answerer):
    res = client.post("/ask", json={"question": "Paano kumuha ng passport?", "lang": "tl"})

    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "Bring your PSA birth certificate [1]."
    assert body["sources"] == [{"title": "Passport", "url": "https://a.gov.ph/p", "agency": "DFA"}]
    assert fake_answerer.calls[0][2] == "tl"


def test_ask_rejects_unknown_language():
    res = client.post("/ask", json={"question": "passport?", "lang": "fr"})
    assert res.status_code == 422


def test_user_message_numbers_by_page_and_sets_language():
    other = RetrievedChunk("Pay online.", "NBI clearance", "https://b.gov.ph/n", "NBI")
    msg = build_user_message("How?", [*CHUNKS, other], "ceb")

    # Both passport chunks share one number, so [n] matches the n-th listed source.
    assert "[1] DFA - Passport (https://a.gov.ph/p)" in msg
    assert "Bring a PSA birth certificate." in msg and "Appointments are online." in msg
    assert "[2] NBI - NBI clearance" in msg
    assert "[3]" not in msg
    assert msg.endswith("Answer in Bisaya (Cebuano).")


def test_ask_cleans_model_specific_citations(fake_answerer):
    fake_answerer.answer = lambda q, c, lang: "Use My.SSS 【1†L1-L4】 and pay 【2】."
    res = client.post("/ask", json={"question": "SSS?"})
    assert res.json()["answer"] == "Use My.SSS [1] and pay [2]."


def test_clean_citations_leaves_normal_text_alone():
    from app.rag import clean_citations

    text = "Bring 2 IDs [1]. Fee is PHP 950 (as of 2026)."
    assert clean_citations(text) == text


def test_sources_only_answerer_explains_missing_key():
    from app.rag import SourcesOnlyAnswerer

    assert "LLM_API_KEY" in SourcesOnlyAnswerer().answer("q", CHUNKS, "en")
